from pydantic import BaseModel, Field, SecretStr, field_validator

class Credentials(BaseModel):
    """Credentials for e-Nabiz login."""
    tc_no: str = Field(..., description="11-digit Turkish Identity Number")
    password: SecretStr = Field(..., description="e-Nabiz password")

    @field_validator('tc_no')
    @classmethod
    def validate_tc_no(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 11:
            raise ValueError("TC number must be exactly 11 digits.")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "tc_no": "12345678901",
                    "password": "my_secure_password"
                }
            ]
        }
    }
