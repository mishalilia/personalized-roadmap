import React, { type ReactNode } from "react";
import Layout from "@theme/Layout";
import BrowserOnly from "@docusaurus/BrowserOnly";

// A learner's public progress, opened from the link they made in their path's settings.
export default function ProgressPage(): ReactNode {
  return (
    <Layout title="Learning progress" description="What a learner finished on their personal path." noFooter>
      <main className="container margin-vert--xl">
        <BrowserOnly fallback={<p>Loading…</p>}>
          {() => {
            const PublicProgress = require("@site/src/components/personal-path/PublicProgress").default;
            return <PublicProgress />;
          }}
        </BrowserOnly>
      </main>
    </Layout>
  );
}
