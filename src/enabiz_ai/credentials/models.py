from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


class Credentials(BaseModel):
    """Credentials for e-Nabız login (supports e-Devlet and ENabız methods).

    At least one of ``password`` (e-Devlet) or ``enabiz_password`` must be
    provided.  Old credential files that only contain ``tc_no`` + ``password``
    are deserialized transparently — the new optional fields simply default.
    """

    tc_no: str = Field(..., description="11-digit Turkish Identity Number")
    password: SecretStr | None = Field(
        default=None, description="e-Devlet password (optional if enabiz_password is set)"
    )
    enabiz_password: SecretStr | None = Field(
        default=None, description="ENabız direct login password"
    )
    twofa_enabled: bool = Field(
        default=True,
        description="Whether 2FA/SMS verification is enabled for this account",
    )

    @field_validator("tc_no")
    @classmethod
    def validate_tc_no(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 11:
            raise ValueError("TC number must be exactly 11 digits.")
        return v

    @model_validator(mode="after")
    def at_least_one_password(self) -> Credentials:
        has_edevlet = self.password is not None and bool(
            self.password.get_secret_value()
        )
        has_enabiz = self.enabiz_password is not None and bool(
            self.enabiz_password.get_secret_value()
        )
        if not has_edevlet and not has_enabiz:
            raise ValueError(
                "At least one of password (e-Devlet) or enabiz_password must be provided."
            )
        return self

    # ── Convenience helpers ────────────────────────────────────────
    @property
    def has_edevlet(self) -> bool:
        """Return True if e-Devlet credentials are configured."""
        return self.password is not None and bool(self.password.get_secret_value())

    @property
    def has_enabiz(self) -> bool:
        """Return True if ENabız direct-login credentials are configured."""
        return self.enabiz_password is not None and bool(
            self.enabiz_password.get_secret_value()
        )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "tc_no": "12345678901",
                    "password": "my_edevlet_password",
                    "enabiz_password": "my_enabiz_password",
                    "twofa_enabled": True,
                }
            ]
        }
    }
