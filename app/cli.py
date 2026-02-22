import typer
import httpx
import json
import os
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from datetime import datetime

app = typer.Typer()
console = Console()

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_KEY = os.getenv("CUSTOM_TRACKER_API_KEY")

@app.callback()
def main(api_key: Optional[str] = typer.Option(None, envvar="CUSTOM_TRACKER_API_KEY", help="API Key for authentication")):
    global API_KEY
    if api_key:
        API_KEY = api_key

@app.command()
def create_module(name: str, schema: str):
    """
    Register a new module.
    schema: JSON string of the schema.
    """
    try:
        schema_dict = json.loads(schema)
    except json.JSONDecodeError:
        console.print("[red]Invalid JSON string for schema[/red]")
        raise typer.Exit(code=1)

    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    with httpx.Client(headers=headers) as client:
        # Note: In Pydantic model it's aliased as 'schema', so we send 'schema' key
        response = client.post(f"{API_URL}/modules", json={"name": name, "schema": schema_dict})
        if response.status_code == 201:
            console.print(f"[green]Module '{name}' created successfully![/green]")
            console.print(response.json())
        else:
            console.print(f"[red]Error creating module: {response.status_code}[/red]")
            console.print(response.text)

@app.command()
def list_modules():
    """
    List all registered modules.
    """
    try:
        headers = {"X-API-Key": API_KEY} if API_KEY else {}
        with httpx.Client(headers=headers) as client:
            response = client.get(f"{API_URL}/modules")
            if response.status_code == 200:
                modules = response.json()
                table = Table(title="Modules")
                table.add_column("ID", justify="right", style="cyan")
                table.add_column("Name", style="magenta")
                table.add_column("Schema", style="green")

                for module in modules:
                    # module["schema"] is used because response model uses populate_by_name=True or similar?
                    # Actually schema uses alias="schema", so output JSON will have "schema".
                    table.add_row(str(module["id"]), module["name"], json.dumps(module.get("schema", {})))

                console.print(table)
            else:
                console.print(f"[red]Error listing modules: {response.status_code}[/red]")
    except httpx.ConnectError:
        console.print(f"[red]Could not connect to API at {API_URL}[/red]")

@app.command()
def create_event(module_id: int, payload: str):
    """
    Create a new event.
    payload: JSON string of the event data.
    """
    try:
        payload_dict = json.loads(payload)
    except json.JSONDecodeError:
        console.print("[red]Invalid JSON string for payload[/red]")
        raise typer.Exit(code=1)

    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    with httpx.Client(headers=headers) as client:
        data = {
            "module_id": module_id,
            "payload": payload_dict
        }
        response = client.post(f"{API_URL}/events", json=data)
        if response.status_code == 201:
            console.print(f"[green]Event created successfully![/green]")
            console.print(response.json())
        else:
            console.print(f"[red]Error creating event: {response.status_code}[/red]")
            console.print(response.text)

@app.command()
def list_events(module_id: Optional[int] = None, user_id: Optional[int] = None):
    """
    List events.
    """
    params = {}
    if module_id:
        params["module_id"] = module_id
    if user_id:
        params["user_id"] = user_id

    try:
        headers = {"X-API-Key": API_KEY} if API_KEY else {}
        with httpx.Client(headers=headers) as client:
            response = client.get(f"{API_URL}/events", params=params)
            if response.status_code == 200:
                events = response.json()
                table = Table(title="Events")
                table.add_column("ID", justify="right", style="cyan")
                table.add_column("User ID", justify="right", style="blue")
                table.add_column("Module ID", justify="right", style="magenta")
                table.add_column("Timestamp", style="yellow")
                table.add_column("Payload", style="green")

                for event in events:
                    table.add_row(
                        str(event["id"]),
                        str(event["user_id"]),
                        str(event["module_id"]),
                        event["timestamp"],
                        json.dumps(event["payload"])
                    )

                console.print(table)
            else:
                console.print(f"[red]Error listing events: {response.status_code}[/red]")
    except httpx.ConnectError:
        console.print(f"[red]Could not connect to API at {API_URL}[/red]")

@app.command()
def aggregate(
    module_id: Optional[int] = typer.Option(None, help="Filter by Module ID"),
    start_date: Optional[datetime] = typer.Option(None, formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"], help="Start date (YYYY-MM-DD)"),
    end_date: Optional[datetime] = typer.Option(None, formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"], help="End date (YYYY-MM-DD)"),
    group_by: Optional[List[str]] = typer.Option(None, help="Group by: module, day, week, month"),
    operation: str = typer.Option("count", help="Operation: count, sum, avg, min, max"),
    target_key: Optional[str] = typer.Option(None, help="Key in payload to aggregate on")
):
    """
    Aggregate events.
    """
    # Build payload
    data = {
        "module_id": module_id,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "group_by": group_by or [],
        "operation": operation,
        "target_key": target_key
    }

    # Remove None values
    data = {k: v for k, v in data.items() if v is not None}

    try:
        headers = {"X-API-Key": API_KEY} if API_KEY else {}
        with httpx.Client(headers=headers) as client:
            response = client.post(f"{API_URL}/analytics/aggregate", json=data)

            if response.status_code == 200:
                results = response.json()
                table = Table(title="Aggregation Results")

                # Determine columns dynamically based on first result
                if results:
                    first_group = results[0]["group"]
                    # Add grouping columns
                    for key in first_group.keys():
                        table.add_column(key.capitalize(), style="cyan")
                    # Add value column
                    table.add_column("Value", style="magenta")

                    for item in results:
                        row = []
                        group = item["group"]
                        for key in first_group.keys():
                            row.append(str(group.get(key, "")))
                        row.append(str(item["value"]))
                        table.add_row(*row)
                else:
                    console.print("[yellow]No results found.[/yellow]")
                    return

                console.print(table)
            else:
                console.print(f"[red]Error aggregating events: {response.status_code}[/red]")
                console.print(response.text)
    except httpx.ConnectError:
        console.print(f"[red]Could not connect to API at {API_URL}[/red]")

if __name__ == "__main__":
    app()
