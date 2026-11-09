from app.agents.checkpoints import checkpoints


def main() -> None:
    with checkpoints() as saver:
        saver.setup()


if __name__ == "__main__":
    main()
