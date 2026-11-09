"""Rotate the dedicated synthetic workspace and preserve its immutable history."""

from scripts.seed_demo import demo_password, seed

if __name__ == "__main__":
    print(f"Demo project {seed(demo_password(), reset=True)}")
