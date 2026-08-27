#!/usr/bin/env python3
"""Simple Canary test for the quickstart tutorial."""

import canary
import canary_pyt

# Add some keywords for filtering
canary_pyt.directives.keywords("quickstart", "demo")

def main():
    instance = canary.get_instance()
    print(f"Hello from {instance.name}!")
    print("This is a Canary test.")

if __name__ == "__main__":
    main()