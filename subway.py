import sys

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        from app.selftest import main

        raise SystemExit(main())

    from app.main import SubwayApp

    app = SubwayApp()
    app.mainloop()
