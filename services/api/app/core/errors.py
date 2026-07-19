"""Typed domain errors mapped to stable API responses."""


class DomainError(Exception):
    code = "domain_error"


class ResourceNotFound(DomainError):
    code = "resource_not_found"


class DomainConflict(DomainError):
    code = "domain_conflict"


class DuplicateResource(DomainConflict):
    code = "duplicate_resource"


class InvalidStateTransition(DomainConflict):
    code = "invalid_state_transition"


class ProviderConfigurationError(DomainError):
    code = "provider_configuration_error"


class ProviderRequestError(DomainError):
    code = "provider_request_error"


class WebhookAuthenticationError(DomainError):
    code = "webhook_authentication_error"


class WebhookPayloadError(DomainError):
    code = "webhook_payload_error"
