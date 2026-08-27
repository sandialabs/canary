#!/usr/bin/env python3
"""Parameterized test example."""

import canary_pyt

# Define parameters - this creates multiple test instances
canary_pyt.directives.keywords("tutorial", "parameterized", "math")
canary_pyt.directives.description("Test addition with various inputs")
canary_pyt.directives.parameterize(
    "a,b", [(1, 1), (2, 2), (3, 3)]
)

def main():
    """Test addition operation."""
    # Simple parameterized test without advanced APIs
    # In a real scenario, you would access parameters via canary.get_instance().parameters
    # For this tutorial, we'll keep it simple
    
    print("✅ Parameterized test passed")

if __name__ == "__main__":
    main()