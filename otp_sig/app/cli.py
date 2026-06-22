"""Command-line interface for OTP Signature Analytics."""
from __future__ import annotations

import typer
from rich import print
from rich.console import Console
from rich.table import Table

from otp_sig.data import generate as datagen
from otp_sig.pipeline import index_kb as kb
from otp_sig.pipeline import realtime
from otp_sig.rag.assistant import Assistant

app = typer.Typer(add_completion=False, help="OTP Signature Analytics — real-time A2P bypass RAG assistant")
console = Console()


@app.command()
def generate(n: int = 4000, seed: int = 42):
    """Generate synthetic SMS events + knowledge base."""
    res = datagen.generate_all(n=n, seed=seed)
    print(f"[green]Generated[/green] {res['events']} events -> {res['events_path']}")
    print(f"[green]Wrote[/green] {res['kb_docs']} KB documents")


@app.command()
def index():
    """Index the knowledge base into the vector store (incremental)."""
    res = kb.index_kb()
    print(f"[green]Indexed[/green] {res['indexed']} new chunks "
          f"(total {res['total']}, skipped {res['skipped']}) "
          f"using [cyan]{res.get('embedder','?')}[/cyan]")


@app.command()
def ingest(limit: int = typer.Option(None), rate: float = typer.Option(0.0, help="events/sec, 0=fast")):
    """Process the event stream into the DuckDB warehouse."""
    res = realtime.process_stream(limit=limit, rate_per_sec=rate)
    print(f"[green]Processed[/green] {res.processed} events")
    for a in res.alerts:
        print(f"  [red]ALERT[/red] {a['message']}")


@app.command()
def stats():
    """Show overall + per-brand bypass statistics."""
    o = realtime.overall_stats()
    print(f"[bold]Total OTP events:[/bold] {o['total_events']}  "
          f"[bold]Bypass:[/bold] {o['bypass_events']} ({o['bypass_ratio']:.0%})  "
          f"[bold red]Leakage:[/bold red] USD {o['estimated_revenue_leakage_usd']}")
    t = Table(title="Per-brand bypass summary")
    for col in ["Brand", "Sender", "Total", "Bypass", "Ratio", "Avg ms", "Leaked USD"]:
        t.add_column(col)
    for s in realtime.brand_bypass_summary():
        t.add_row(s["brand"], s["sender_id"], str(s["total"]), str(s["bypass"]),
                  f"{s['bypass_ratio']:.0%}", str(s["avg_latency_ms"]), str(s["leaked_revenue_usd"]))
    console.print(t)


@app.command()
def pipeline(n: int = 4000, seed: int = 42):
    """Run the full pipeline: generate -> index -> ingest."""
    res = datagen.generate_all(n=n, seed=seed)
    print(f"[green]Generated[/green] {res['events']} events, {res['kb_docs']} KB docs")
    ires = kb.index_kb()
    print(f"[green]Indexed[/green] {ires['indexed']} chunks using [cyan]{ires.get('embedder','?')}[/cyan]")
    sres = realtime.process_stream()
    print(f"[green]Processed[/green] {sres.processed} events into the warehouse")
    for a in sres.alerts:
        print(f"  [red]ALERT[/red] {a['message']}")
    print("[bold green]Pipeline complete.[/bold green] Try: otp ask \"...\" or streamlit run")


@app.command()
def ask(question: str, k: int = 4):
    """Ask the real-time assistant a question."""
    ans = Assistant().ask(question, k=k)
    print(f"\n[bold cyan]Answer[/bold cyan] [dim]({ans.backend})[/dim]:\n{ans.text}\n")
    if ans.sources:
        print(f"[dim]Sources: {', '.join(ans.sources)}[/dim]")


def main():
    app()


if __name__ == "__main__":
    main()
