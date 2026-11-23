# The online demo (learn mode on a static host)

The lessons can run as a public website with no server: [frontend/vercel.json](../frontend/vercel.json)
builds it on [Vercel](https://vercel.com) (free Hobby plan), and any static host (GitHub
Pages, Cloudflare Pages, Netlify) can serve the same folder.

## How it works

A static host only serves files, so it cannot run Python. Instead, the build runs the Python
backend once and saves its answers:

1. `npm run build:site` builds the normal UI in its **site mode** into `frontend/dist-site`. The only
   difference is the transport in `frontend/src/lib/api.js`: instead of calling the server,
   it calls `frontend/src/lib/static/backend.js`, which answers the same `/api/...` requests
   from files. Everything else in the UI is unchanged.
2. `python -m spektrify.server.snapshot frontend/dist-site/data` drives the real API
   (`server/routes.dispatch`) for every demo cube and every preprocessing pipeline the lessons
   use, and saves the responses: the cube itself (float16), the quality report, PCA / anomaly /
   summary maps, the 3-D volume and point cloud, every band-math expression in the lessons,
   and an answer key per task (made by running the real grader over every possible answer).
3. In the browser, cheap per-pixel reads (hover spectra, pins, regions, line profiles,
   thumbnails, the spectral angle to a pinned pixel) are computed from the shipped cube in
   `frontend/src/lib/static/cubeops.js`, so the viewer stays interactive.

`scripts/build-site.sh` runs both steps. Nothing is committed: the site is rebuilt from the
lesson files on every deploy, so a new or edited lesson goes online with the next push.

What the online demo can't do: open or upload files, run a preprocessing pipeline or a
band-math expression that no lesson uses, or show PCA components beyond the first few. It
says so and points to `pip install spektrify`. Answers are checked in the browser, so a
determined learner can read them from the data files; that's fine for a demo.

Size: about 85 MB on the host; a visitor downloads about 5 MB per demo cube they open, plus
what each view needs.

## Build and preview locally

```bash
bash scripts/build-site.sh                 # needs uv and Node 22
python -m http.server -d frontend/dist-site 8000   # then open http://localhost:8000
```

CI builds the site on every pull request (job `site`) and keeps it as a downloadable
artifact for a week.

## Connecting Vercel (one time)

1. Sign in at [vercel.com](https://vercel.com) with your GitHub account (the free Hobby plan
   is enough).
2. Click **Add New… → Project**, find `spektrify` in the list and click **Import**. If it isn't
   listed, click **Adjust GitHub App Permissions** and give Vercel access to the repository.
3. **Root Directory**: pick **`frontend`**. Leave everything else as it is:
   `frontend/vercel.json` sets the build command (which runs `scripts/build-site.sh` from the
   repository root), the output folder and "no framework". Click **Deploy**. The first build
   takes a few minutes.
4. You get an address like `spektrify.vercel.app`. Every push to `main` updates it, and
   every pull request gets its own preview link (Vercel comments it on the PR).

If the project already exists with another root directory, change it under **Settings →
Build and Deployment → Root Directory**, then redeploy. Keep "Include files outside the root
directory in the Build Step" switched on (the default): the build needs the Python package.

A custom domain can be added later under **Project → Settings → Domains**.
