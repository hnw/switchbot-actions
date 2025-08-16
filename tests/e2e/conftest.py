import json

import pytest
import pytest_asyncio
import yaml
from aiohttp import web


@pytest_asyncio.fixture
async def webhook_server():
    """
    Fixture for a simple aiohttp webhook server.
    It captures the last received request.
    """
    app = web.Application()
    received_requests = []

    async def handler(request):
        data = None
        if request.can_read_body:
            try:
                data = await request.json()
            except json.JSONDecodeError:
                data = await request.text()
        received_requests.append(
            {
                "method": request.method,
                "headers": dict(request.headers),
                "path": request.path,
                "query": dict(request.query),
                "body": data,
            }
        )
        return web.Response(text="OK")

    app.router.add_route("*", "/webhook", handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 8080)
    await site.start()

    yield received_requests

    await runner.cleanup()


@pytest.fixture
def config_generator(tmp_path):
    """
    Fixture to generate dynamic config.yaml files for tests.
    """

    def _generate_config(config_content: dict):
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_content, f)
        return config_path

    return _generate_config
