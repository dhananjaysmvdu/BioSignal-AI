#!/usr/bin/env python3
"""
CLI wrapper for human approval API.
Commands: request, status, grant, override
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))
import human_approval_api as api


def cmd_status():
    """Show current approval status."""
    status = api.get_status()
    print(json.dumps(status, indent=2))


def cmd_request(args):
    """Request approval."""
    result = api.request_approval(args.requester, args.reason)
    print(json.dumps(result, indent=2))
    
    if "approval_id" in result:
        print(f"\n✓ Request created: {result['approval_id']}", file=sys.stderr)
        print(f"  Use 'grant --id {result['approval_id']}' to approve", file=sys.stderr)


def cmd_grant(args):
    """Grant approval."""
    result = api.grant_approval(args.id, args.approver)
    
    if "error" in result:
        print(json.dumps(result, indent=2))
        sys.exit(1)
    else:
        print(json.dumps(result, indent=2))
        print(f"\n✓ Approval granted by {result['approver']}", file=sys.stderr)


def cmd_override(args):
    """Emergency override."""
    result = api.override_approval(args.key, args.id, args.requester, args.reason)
    
    if "error" in result:
        print(json.dumps(result, indent=2))
        sys.exit(1)
    else:
        print(json.dumps(result, indent=2))
        print(f"\n⚠ Emergency override applied for {result['approval_id']}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Human-in-the-loop approval CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # status
    subparsers.add_parser("status", help="Show current approval status")
    
    # request
    req_parser = subparsers.add_parser("request", help="Request approval")
    req_parser.add_argument("--requester", required=True, help="Requester name")
    req_parser.add_argument("--reason", required=True, help="Reason for approval")
    
    # grant
    grant_parser = subparsers.add_parser("grant", help="Grant approval")
    grant_parser.add_argument("--id", required=True, help="Approval ID")
    grant_parser.add_argument("--approver", required=True, help="Approver name")
    
    # override
    override_parser = subparsers.add_parser("override", help="Emergency override")
    override_parser.add_argument("--key", required=True, help="Override key")
    override_parser.add_argument("--id", required=True, help="Approval ID")
    override_parser.add_argument("--requester", required=True, help="Requester name")
    override_parser.add_argument("--reason", required=True, help="Reason")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == "status":
        cmd_status()
    elif args.command == "request":
        cmd_request(args)
    elif args.command == "grant":
        cmd_grant(args)
    elif args.command == "override":
        cmd_override(args)


if __name__ == "__main__":
    main()
