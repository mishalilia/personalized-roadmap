import React, { type ReactNode } from "react";
import Layout from "@theme/Layout";
import BrowserOnly from "@docusaurus/BrowserOnly";

// For the course team: where learners who share their progress stop (API_REVIEWER_EMAILS on the API).
export default function ReportPage(): ReactNode {
  return (
    <Layout title="Where learners stop" description="Drop-off by module, for the course team." noFooter>
      <main className="container margin-vert--xl">
        <BrowserOnly fallback={<p>Loading…</p>}>
          {() => {
            const CourseReport = require("@site/src/components/personal-path/CourseReport").default;
            return <CourseReport />;
          }}
        </BrowserOnly>
      </main>
    </Layout>
  );
}
