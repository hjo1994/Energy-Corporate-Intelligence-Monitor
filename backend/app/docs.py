from fastapi import APIRouter, FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from swagger_ui_bundle import swagger_ui_path

router = APIRouter(include_in_schema=False)


@router.get("/api/docs")
def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title="AI Cockpit API",
        swagger_js_url="/api/static/swagger-ui-bundle.js",
        swagger_css_url="/api/static/swagger-ui.css",
    )


def add_static_files(app: FastAPI):

    app.mount(
        "/api/static",
        StaticFiles(directory=swagger_ui_path),
        name="static",
    )

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )

        schema["openapi"] = "3.0.3"
        app.openapi_schema = schema

        return schema

    app.openapi = custom_openapi