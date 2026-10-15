import sys

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        from app.selftest import main

        log = None
        if "--log" in sys.argv:
            index = sys.argv.index("--log") + 1
            log = sys.argv[index] if index < len(sys.argv) else None
        raise SystemExit(main(log))

    from app.main import SubwayApp

    app = SubwayApp()
    app.mainloop()
