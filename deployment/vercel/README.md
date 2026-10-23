# Deploy the portal frontend to Vercel

The browser downloads this static interface from Vercel and connects directly to
an authenticated HTTPS API on the Jetson. The API proxies the existing camera;
H.264 video and sampled JPEG fallback use the same private access token. The
camera's local management interface is not exposed to the browser. Vercel does
not run the queue, worker, SQLite database, or long-lived video connection.

## Vercel project settings

1. Import this GitHub repository and select the branch containing this work.
2. Set **Root Directory** to `deployment/vercel` and enable **Include source files
   outside of the Root Directory in the Build Step**. The build reads only the
   allowlisted assets in `src/cartpole_sdk/portal/web`.
3. Choose framework **Other**. Build command is `node build.mjs`; leave Output
   Directory unset and use the empty Install Command from `vercel.json`.
4. Set `CARTPOLE_API_ORIGIN` to the Jetson's reachable HTTPS origin, for example
   `https://your-jetson.example.ts.net`. This value is public configuration, not
   a secret. Do not place access tokens in Vercel environment variables.
5. Deploy. Configure the Jetson API's allowed browser origins to include the exact
   resulting URL (`https://your-project.vercel.app`). Custom domains and preview
   URLs need their own explicit entries; do not allow all `*.vercel.app` origins.
6. Open the portal and enter the separately supplied private submitter/operator
   token. Choose **Live view**, start the preview, and select **Camera**,
   **Tracking**, or **Green mask**. Presentation is shared across camera viewers.

The API must already be reachable over HTTPS and permit the frontend origin.
The browser cannot reach a laptop's `localhost` tunnel from a hosted page.
Deploying this static site does not itself attach an execution worker or grant
physical run approval. Reservations retain their separate server configuration.

The build fails if the API origin uses HTTP, contains credentials, or includes a
path/query/fragment. It generates a Content Security Policy allowing network
requests only to this exact origin and the frontend itself. Tokens stay in
session storage and are sent in Authorization headers, never URL parameters.
Authentication failures and HTTPS/CORS connectivity errors must be resolved on
the API; changing the frontend does not bypass access controls.

## Local build check

```sh
cd deployment/vercel
CARTPOLE_API_ORIGIN=https://your-jetson.example.ts.net node build.mjs
```

Only five public files appear in `.vercel/output/static`: `index.html`,
`style.css`, `app.js`, `video.js`, and generated `config.js`. `.vercel/output/config.json`
contains Vercel routing and security headers. The build has no package dependencies.

Deployment format: [Vercel Build Output API](https://vercel.com/docs/build-output-api)
and [Build Output configuration](https://vercel.com/docs/build-output-api/configuration).
