# Campus Customs Ops Desk (frontend)

React + Vite + TypeScript board for the Campus Customs agent team.

```bash
npm install
npm run dev        # http://localhost:5173
```

It calls the FastAPI backend at `http://localhost:8000`. To use a different address, set `VITE_API_URL`. Start the backend first from `backend/` with `uvicorn main:app --reload --port 8000`.

The design is explained in `../output/design.md`.
