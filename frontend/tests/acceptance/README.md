# Frontend acceptance specs (locked)

Definition of done for the UI features in `/features.json`. They fix the contract between the page and
the tests through `data-testid` attributes. Run against a live stack:

    FAKE_LLM=1 scripts/dev.sh           # in one terminal
    cd frontend && pnpm exec playwright test   # in another

Sessions cannot edit this directory; only Padraig changes it.
