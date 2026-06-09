import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from zeropark_gateway.main import app
from zeropark_gateway.exceptions import AppException

router = APIRouter()

@router.get("/test/app-exception")
def raise_app_exception():
    raise AppException("Custom error occurred", error_code="CUSTOM_ERR", status_code=400, details={"info": "test"})

@router.get("/test/unhandled-exception")
def raise_unhandled():
    raise ValueError("Something completely unexpected")

@router.post("/test/validation")
def trigger_validation(data: dict):
    # This won't trigger 422 by itself since it's just dict, need a Pydantic model
    pass

from pydantic import BaseModel
class DummyModel(BaseModel):
    required_field: str

@router.post("/test/validation-model")
def trigger_validation_model(data: DummyModel):
    return data

app.include_router(router)
client = TestClient(app, raise_server_exceptions=False)

def test_app_exception_handler():
    response = client.get("/test/app-exception")
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "CUSTOM_ERR"
    assert data["error"]["message"] == "Custom error occurred"
    assert data["error"]["details"]["info"] == "test"

def test_unhandled_exception_handler():
    # Will trigger a 500 error handled by global Exception handler
    response = client.get("/test/unhandled-exception")
    assert response.status_code == 500
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "unexpected error" in data["error"]["message"]

def test_validation_exception_handler():
    # Sending invalid payload to trigger 422 RequestValidationError
    response = client.post("/test/validation-model", json={"invalid": "payload"})
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "details" in data["error"]
    assert "errors" in data["error"]["details"]
