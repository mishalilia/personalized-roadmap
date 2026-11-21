import React, { type ReactNode } from "react";
import Layout from "@theme/Layout";
import BrowserOnly from "@docusaurus/BrowserOnly";

// For course reviewers: the capstone projects learners submitted (API_REVIEWER_EMAILS on the API).
export default function ReviewPage(): ReactNode {
  return (
    <Layout title="Reviews" description="Submitted capstone projects." noFooter>
      <main className="container margin-vert--xl">
        <BrowserOnly fallback={<p>Loading…</p>}>
          {() => {
            const Review = require("@site/src/components/personal-path/Review").default;
            return <Review />;
          }}
        </BrowserOnly>
      </main>
    </Layout>
  );
}
