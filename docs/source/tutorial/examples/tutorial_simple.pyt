#!/usr/bin/env python3
"""Simple tutorial example without advanced features."""

import canary_pyt

# Basic metadata
canary_pyt.directives.keywords("tutorial", "simple")
canary_pyt.directives.description("A simple tutorial test")

def main():
    # Simple test logic
    result = 2 + 2
    expected = 4
    
    # Basic validation
    assert result == expected, f"Expected {expected}, got {result}"
    
    # Simple output
    print(f"✅ Test passed: {result} == {expected}")

if __name__ == "__main__":
    main()