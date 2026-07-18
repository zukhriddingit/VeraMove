# Intake agent boundary

Owner: Toheeb (@Olacode01). The future intake agent receives a voice-interview transcript or parsed quote/inventory document and must return a `JobSpecV1`. It may ask only moving questions configured in `configs/moving.yaml`. It must distinguish unknown values from confirmed values, preserve nullable future Vera identifiers, and never invent inventory or access facts.

This starter invokes no model or telephony service. Tests and demos use synthetic fixtures only.
