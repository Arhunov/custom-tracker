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
def create_module(
    name: Optional[str] = typer.Argument(None, help="Module name"),
    schema: Optional[str] = typer.Argument(None, help="JSON string of the schema"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Path to JSON file containing module definition (name and schema) or just schema")
):
    """
    Register a new module.
    """
    schema_dict = {}

    if file:
        if not os.path.exists(file):
            console.print(f"[red]File not found: {file}[/red]")
            raise typer.Exit(code=1)

        try:
            with open(file, "r") as f:
                file_content = json.load(f)
            if not isinstance(file_content, dict):
                 console.print(f"[red]Invalid JSON content in file: {file} (must be a dictionary)[/red]")
                 raise typer.Exit(code=1)
        except json.JSONDecodeError:
            console.print(f"[red]Invalid JSON in file: {file}[/red]")
            raise typer.Exit(code=1)

        # If name is not provided, try to find it in the file
        if not name:
            if "name" in file_content and "schema" in file_content:
                name = file_content["name"]
                schema_dict = file_content["schema"]
            else:
                console.print("[red]Name not provided and not found in file (expected 'name' and 'schema' keys).[/red]")
                raise typer.Exit(code=1)
        else:
            # If name is provided, the file is treated as the schema
            # Check if file has "schema" key or is the schema itself
            if "schema" in file_content:
                 schema_dict = file_content["schema"]
            else:
                 schema_dict = file_content

    elif name and schema:
        try:
            schema_dict = json.loads(schema)
        except json.JSONDecodeError:
            console.print("[red]Invalid JSON string for schema[/red]")
            raise typer.Exit(code=1)
    else:
        console.print("[red]Missing arguments: either provide name and schema, or use --file[/red]")
        raise typer.Exit(code=1)

    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    with httpx.Client(headers=headers) as client:
        response = client.post(f"{API_URL}/modules", json={"name": name, "schema": schema_dict})
        if response.status_code == 201:
            console.print(f"[green]Module '{name}' created successfully![/green]")
            console.print_json(data=response.json())
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
                table = Table(title="Modules", show_lines=True)
                table.add_column("ID", justify="right", style="cyan", no_wrap=True)
                table.add_column("Name", style="magenta")
                table.add_column("Schema", style="green", overflow="fold")

                for module in modules:
                    # module["schema"] is used because response model uses populate_by_name=True or similar?
                    # Actually schema uses alias="schema", so output JSON will have "schema".
                    table.add_row(str(module["id"]), module["name"], json.dumps(module.get("schema", {}), indent=2))

                console.print(table)
            else:
                console.print(f"[red]Error listing modules: {response.status_code}[/red]")
    except httpx.ConnectError:
        console.print(f"[red]Could not connect to API at {API_URL}[/red]")

@app.command()
def create_event(
    module_id: int = typer.Argument(..., help="Module ID"),
    payload: Optional[str] = typer.Argument(None, help="JSON string of the event data"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Path to JSON file containing payload")
):
    """
    Create a new event.
    """
    payload_dict = {}

    if file:
        if not os.path.exists(file):
            console.print(f"[red]File not found: {file}[/red]")
            raise typer.Exit(code=1)

        try:
            with open(file, "r") as f:
                payload_dict = json.load(f)
            if not isinstance(payload_dict, dict):
                 console.print(f"[red]Invalid JSON content in file: {file} (must be a dictionary)[/red]")
                 raise typer.Exit(code=1)
        except json.JSONDecodeError:
            console.print(f"[red]Invalid JSON in file: {file}[/red]")
            raise typer.Exit(code=1)

        # If payload argument is also provided, warn or error?
        # For now, file takes precedence if both are present, or we can error.
        # But since payload is optional, it might be None.

    elif payload:
        try:
            payload_dict = json.loads(payload)
        except json.JSONDecodeError:
            console.print("[red]Invalid JSON string for payload[/red]")
            raise typer.Exit(code=1)
    else:
        console.print("[red]Missing arguments: provide payload string or use --file[/red]")
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
            console.print_json(data=response.json())
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
                table = Table(title="Events", show_lines=True)
                table.add_column("ID", justify="right", style="cyan", no_wrap=True)
                table.add_column("User ID", justify="right", style="blue")
                table.add_column("Module ID", justify="right", style="magenta")
                table.add_column("Timestamp", style="yellow")
                table.add_column("Payload", style="green", overflow="fold")

                for event in events:
                    table.add_row(
                        str(event["id"]),
                        str(event["user_id"]),
                        str(event["module_id"]),
                        event["timestamp"],
                        json.dumps(event["payload"], indent=2)
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
                table = Table(title="Aggregation Results", show_lines=True)

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

@app.command()
def export(
    filename: Optional[str] = typer.Option(None, help="Output filename"),
    format: str = typer.Option("json", help="Format: json or csv"),
    start_date: Optional[datetime] = typer.Option(None, formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"], help="Start date (YYYY-MM-DD)"),
    end_date: Optional[datetime] = typer.Option(None, formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"], help="End date (YYYY-MM-DD)"),
    module_id: Optional[int] = typer.Option(None, help="Filter by Module ID")
):
    """
    Export data to a file.
    """
    params = {"format": format}
    if start_date:
        params["start_date"] = start_date.isoformat()
    if end_date:
        params["end_date"] = end_date.isoformat()
    if module_id:
        params["module_id"] = module_id

    try:
        headers = {"X-API-Key": API_KEY} if API_KEY else {}
        with httpx.Client(headers=headers, timeout=60.0) as client:
            # Using stream=True for large files
            with client.stream("GET", f"{API_URL}/data/export", params=params) as response:
                if response.status_code == 200:
                    # Determine filename if not provided
                    if not filename:
                        content_disposition = response.headers.get("content-disposition")
                        if content_disposition and "filename=" in content_disposition:
                            filename = content_disposition.split("filename=")[1].strip('"')
                        else:
                            filename = f"export_{datetime.now().strftime('%Y%m%d%H%M%S')}.{format}"

                    with open(filename, "wb") as f:
                        for chunk in response.iter_bytes():
                            f.write(chunk)

                    console.print(f"[green]Data exported successfully to {filename}[/green]")
                else:
                    console.print(f"[red]Error exporting data: {response.status_code}[/red]")
                    console.print(response.read().decode()) # read remaining content
    except httpx.ConnectError:
        console.print(f"[red]Could not connect to API at {API_URL}[/red]")
    except Exception as e:
        console.print(f"[red]An error occurred: {str(e)}[/red]")

@app.command(name="import")
def import_data(
    filename: str = typer.Argument(..., help="File to import")
):
    """
    Import data from a file (JSON or CSV).
    """
    if not os.path.exists(filename):
        console.print(f"[red]File not found: {filename}[/red]")
        raise typer.Exit(code=1)

    try:
        headers = {"X-API-Key": API_KEY} if API_KEY else {}
        # We need to determine content type or just let httpx handle it?
        # httpx handles file uploads if we pass 'files'

        with open(filename, "rb") as f:
            files = {"file": (os.path.basename(filename), f)}
            with httpx.Client(headers=headers, timeout=60.0) as client:
                response = client.post(f"{API_URL}/data/import", files=files)

                if response.status_code == 200:
                    result = response.json()
                    console.print("[green]Import completed![/green]")
                    console.print(f"Success: {result['success_count']}")
                    console.print(f"Failures: {result['failure_count']}")
                    if result['errors']:
                        console.print("[yellow]Errors (first 10):[/yellow]")
                        for error in result['errors']:
                            console.print(f"- {error}")
                else:
                    console.print(f"[red]Error importing data: {response.status_code}[/red]")
                    console.print(response.text)

    except httpx.ConnectError:
        console.print(f"[red]Could not connect to API at {API_URL}[/red]")
    except Exception as e:
        console.print(f"[red]An error occurred: {str(e)}[/red]")

@app.command()
def create_webhook(
    url: str = typer.Argument(..., help="Webhook URL"),
    module_id: Optional[int] = typer.Option(None, help="Module ID to filter by"),
    event_type: str = typer.Option("event.created", help="Event type to trigger on")
):
    """
    Register a new webhook.
    """
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    data = {
        "url": url,
        "module_id": module_id,
        "event_type": event_type
    }
    # Remove None values
    data = {k: v for k, v in data.items() if v is not None}

    with httpx.Client(headers=headers) as client:
        response = client.post(f"{API_URL}/webhooks", json=data)
        if response.status_code == 201:
            console.print(f"[green]Webhook created successfully![/green]")
            console.print_json(data=response.json())
        else:
            console.print(f"[red]Error creating webhook: {response.status_code}[/red]")
            console.print(response.text)

@app.command()
def list_webhooks():
    """
    List all registered webhooks for the user.
    """
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    try:
        with httpx.Client(headers=headers) as client:
            response = client.get(f"{API_URL}/webhooks")
            if response.status_code == 200:
                webhooks = response.json()
                table = Table(title="Webhooks", show_lines=True)
                table.add_column("ID", justify="right", style="cyan", no_wrap=True)
                table.add_column("Module ID", justify="right", style="magenta")
                table.add_column("URL", style="green", overflow="fold")
                table.add_column("Event Type", style="yellow")

                for webhook in webhooks:
                    table.add_row(
                        str(webhook["id"]),
                        str(webhook.get("module_id", "") or "All"),
                        webhook["url"],
                        webhook["event_type"]
                    )
                console.print(table)
            else:
                console.print(f"[red]Error listing webhooks: {response.status_code}[/red]")
    except httpx.ConnectError:
        console.print(f"[red]Could not connect to API at {API_URL}[/red]")

@app.command()
def delete_webhook(webhook_id: int = typer.Argument(..., help="Webhook ID")):
    """
    Delete a webhook.
    """
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    try:
        with httpx.Client(headers=headers) as client:
            response = client.delete(f"{API_URL}/webhooks/{webhook_id}")
            if response.status_code == 204:
                console.print(f"[green]Webhook {webhook_id} deleted successfully![/green]")
            elif response.status_code == 404:
                 console.print(f"[red]Webhook {webhook_id} not found.[/red]")
            else:
                console.print(f"[red]Error deleting webhook: {response.status_code}[/red]")
                console.print(response.text)
    except httpx.ConnectError:
        console.print(f"[red]Could not connect to API at {API_URL}[/red]")

if __name__ == "__main__":
    app()
