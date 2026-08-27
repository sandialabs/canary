#!/usr/bin/env python3
"""Simple parameterized tutorial example."""

import canary_pyt

# Parameterized test
canary_pyt.directives.keywords("tutorial", "param")
canary_pyt.directives.parameterize("value", [1, 2, 3])

def main():
    # Get parameters from environment (simplified for tutorial)
    import os
    value = int(os.environ.get("CANARY_PARAM_value", 1))
    
    # Simple calculation
    result = value * 2
    
    # Output results
    print(f"Doubled {value} -> {result}")

if __name__ == "__main__":
    main()