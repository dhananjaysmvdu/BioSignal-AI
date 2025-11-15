# Human Approval API Documentation

## Overview
The Human-in-the-Loop Approval API provides a secure request/grant workflow for sensitive governance actions. All approvals are signed, rate-limited, and auditable.

## Architecture

### Components
- **API** (`human_approval_api.py`): Core functions for request/grant/override
- **CLI** (`human_approval_cli.py`): Command-line wrapper
- **Verifier** (`verify_approval.py`): Validate approval for CI gates
- **Signature Utils** (`signature_utils.py`): HMAC-SHA256 or PGP signing
- **Chain Verifier** (`verify_signatures.py`): Integrity verification

### State Files
- `state/approval_state.json`: Current approval status
- `state/approval_requests.jsonl`: Append-only request log
- `state/approval_highwater.json`: Daily grant limits per approver

## API Endpoints

### GET /approval/status
Returns current approval state.

**Response:**
```json
{
  "status": "unlocked|pending_approval|approved",
  "approval_id": "uuid-string",
  "approver": "name",
  "last_updated": "ISO8601"
}
```

### POST /approval/request
Create new approval request.

**Parameters:**
- `requester` (string, required): Name of requester
- `reason` (string, required): Justification for approval

**Response:**
```json
{
  "approval_id": "91d95678-11e6-4d0c-b09c-72c5b42bc54b",
  "status": "requested",
  "message": "Approval request created: ..."
}
```

**Side Effects:**
- Writes to `approval_requests.jsonl`
- Updates `approval_state.json` to `pending_approval`
- Appends audit marker: `<!-- HUMAN_APPROVAL: REQUESTED <ISO8601> -->`

### POST /approval/grant
Grant an existing approval request.

**Parameters:**
- `approval_id` (string, required): UUID from request
- `approver` (string, required): Name of approver

**Response:**
```json
{
  "approval_id": "...",
  "status": "granted",
  "approver": "bob",
  "signature": "7ecb0a6557ca71cb05cbce85b783019f877aec8e9b8b18e3eab603c9da76a7af",
  "message": "Approval granted successfully"
}
```

**Side Effects:**
- Updates request in `approval_requests.jsonl` to `status=granted`
- Adds `signature_meta` with HMAC-SHA256 signature
- Updates `approval_state.json` to `approved`
- Increments `approval_highwater.json` for approver
- Appends audit marker: `<!-- HUMAN_APPROVAL: GRANTED <ISO8601> -->`

**Rate Limiting:**
- Default: 5 grants per approver per day
- Returns HTTP 403 if limit exceeded
- Appends marker: `<!-- APPROVAL_LIMIT: EXCEEDED <ISO8601> -->`

### POST /approval/override
Emergency override (requires `OVERRIDE_KEY` env var).

**Parameters:**
- `override_key` (string, required): Secret override key
- `approval_id` (string, required): UUID to grant
- `requester` (string, required): Original requester
- `reason` (string, required): Override reason

**Response:**
```json
{
  "approval_id": "...",
  "status": "granted",
  "approver": "OVERRIDE",
  "message": "Emergency override applied"
}
```

**Side Effects:**
- Creates granted request with `approver=OVERRIDE`
- Signature method: `override`
- Appends marker: `<!-- APPROVAL_OVERRIDE: USED <ISO8601> -->`

## CLI Usage

### Status
```bash
python scripts/supervision/human_approval_cli.py status
```

### Request Approval
```bash
python scripts/supervision/human_approval_cli.py request \
  --requester "alice" \
  --reason "Emergency threshold override"
```

Output includes `approval_id` for granting.

### Grant Approval
```bash
export SIGNING_SECRET="your-secret-key"
python scripts/supervision/human_approval_cli.py grant \
  --id "91d95678-11e6-4d0c-b09c-72c5b42bc54b" \
  --approver "bob"
```

### Emergency Override
```bash
export OVERRIDE_KEY="emergency-key"
python scripts/supervision/human_approval_cli.py override \
  --key "$OVERRIDE_KEY" \
  --id "new-uuid-1234" \
  --requester "system" \
  --reason "Critical production fix"
```

## CI Integration

### Approval Gate Workflow
Use `.github/workflows/approval_gate.yml` to gate protected jobs:

```yaml
name: Deploy Production
on:
  workflow_dispatch:
    inputs:
      approval_id:
        description: 'Approval ID from request'
        required: true
        type: string

jobs:
  verify-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Verify Approval
        run: |
          python scripts/supervision/verify_approval.py \
            --id "${{ github.event.inputs.approval_id }}" \
            --ttl 72
        env:
          SIGNING_SECRET: ${{ secrets.SIGNING_SECRET }}
      
      - name: Deploy
        if: success()
        run: ./deploy.sh
```

### Verification Script
`verify_approval.py` checks:
- Approval ID exists in `approval_requests.jsonl`
- Status is `granted`
- Signature is valid
- Grant timestamp within TTL (default 72 hours)

Exit codes:
- `0`: Valid approval
- `1`: Invalid/expired/missing

On failure, appends: `<!-- APPROVAL_GATE: DENIED <ISO8601> -->`

## Signature Verification

### Methods
1. **HMAC-SHA256** (default): Requires `SIGNING_SECRET` env var
2. **PGP-like stub**: Requires `SIGNING_KEY` env var (placeholder for production GPG)
3. **Unsigned**: Fallback (hash-only, weak - dev use only)

### Canonical Payload
```
approval_id|requester|reason|timestamp|status
```

### Signature Metadata
```json
{
  "method": "hmac-sha256",
  "signature": "7ecb0a6557...",
  "signed_hash": "abc123...",
  "approver": "bob",
  "grant_timestamp": "2025-11-14T19:06:00Z"
}
```

### Chain Verification
```bash
python scripts/supervision/verify_signatures.py
```

Checks:
- All granted approvals have valid signatures
- `prev_hash` links are correct (if present)
- No tampering detected

## Safety Features

### Atomic Writes
- All state changes use atomic write-then-rename
- Retries: 1s, 3s, 9s
- On persistent failure: Creates `fix/trust-approval-<timestamp>` branch with diagnostics

### Idempotent Audit Markers
- Markers like `<!-- HUMAN_APPROVAL: GRANTED ... -->` are deduplicated
- Previous markers removed before appending new one

### Rate Limiting
- `approval_highwater.json` tracks daily grants per approver
- Default limit: 5/day
- Configurable via `limit` parameter

### TTL Enforcement
- Granted approvals expire after TTL (default 72h)
- Checked by `verify_approval.py`

### Fix Branch Creation
On atomic write failure:
```
fix/trust-approval-20251114T190000Z/
  diag.json  # Contains error, file path, timestamp, cwd
```

## Error Handling

### Common Errors

**"No approval requests found"**
- No `approval_requests.jsonl` file
- Solution: Create first request via CLI

**"Approval ID not found"**
- UUID doesn't exist in records
- Solution: Check `approval_requests.jsonl` or request new approval

**"Daily approval limit exceeded"**
- Approver has granted 5+ today
- Solution: Wait until next day or use different approver

**"Signature verification failed"**
- `SIGNING_SECRET` mismatch
- Payload tampered
- Solution: Check env var, verify file integrity

**"Approval expired"**
- Grant timestamp > TTL hours ago
- Solution: Request new approval

## Production Deployment

### Environment Variables
```bash
export SIGNING_SECRET="production-hmac-secret-key"
export SIGNING_KEY="path/to/gpg-key"  # Optional, for PGP
export OVERRIDE_KEY="emergency-override-key"  # Highly restricted
```

### Secret Rotation
1. Generate new `SIGNING_SECRET`
2. Update env vars in CI/CD
3. Old approvals remain valid (signatures verified against original secret)
4. New approvals use new secret

### Monitoring
- Check `approval_requests.jsonl` for anomalous patterns
- Alert on `APPROVAL_OVERRIDE: USED` markers
- Track daily grant counts in `approval_highwater.json`

### Backup
- `approval_requests.jsonl` is append-only audit log
- Backup daily to immutable storage
- Verify chain integrity: `verify_signatures.py`

## Testing

### Unit Tests
```bash
python -m pytest tests/supervision/ -v
```

36 tests covering:
- API functions (request, grant, override, limits)
- Signature creation and verification
- Approval verification (valid, expired, missing)
- Atomic write retries and fix-branch creation
- Audit marker idempotency

### Manual Testing
```bash
# Request
python scripts/supervision/human_approval_cli.py request \
  --requester "test-user" --reason "Test flow"

# Capture approval_id from output

# Grant
export SIGNING_SECRET="test-secret"
python scripts/supervision/human_approval_cli.py grant \
  --id "<approval_id>" --approver "test-approver"

# Verify
python scripts/supervision/verify_approval.py --id "<approval_id>"

# Chain integrity
python scripts/supervision/verify_signatures.py
```

## References
- **API**: `scripts/supervision/human_approval_api.py`
- **CLI**: `scripts/supervision/human_approval_cli.py`
- **Verifier**: `scripts/supervision/verify_approval.py`
- **Signatures**: `scripts/supervision/signature_utils.py`
- **Chain Verifier**: `scripts/supervision/verify_signatures.py`
- **Portal**: `portal/approval.html`
- **Workflow**: `.github/workflows/approval_gate.yml`
- **Tests**: `tests/supervision/`
