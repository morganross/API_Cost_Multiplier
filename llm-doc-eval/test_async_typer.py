import typer
import asyncio

app = typer.Typer()

async def hello():
    print("Hello!")
    await asyncio.sleep(0.1) # Simulate async work
    print("Async work done.")

if __name__ == "__main__":
    typer.run(hello)