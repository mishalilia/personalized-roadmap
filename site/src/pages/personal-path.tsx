import React, { type ReactNode } from "react";
import Layout from "@theme/Layout";
import BrowserOnly from "@docusaurus/BrowserOnly";

export default function PersonalPathPage(): ReactNode {
  return (
    <Layout
      title="Your personal path"
      description="Answer a few questions and get a path through the curriculum: which modules to study, which to prove and which to skip, each with a reason."
    >
      <main className="container margin-vert--lg">
        <h1>Your personal path</h1>
        <p>
          Answer a few questions about what you have done and what you want to do. For every module
          you get a suggestion — study it, prove you already know it with its checklist, or skip it —
          with a reason. You can change any of them before you confirm the path.
        </p>
        <BrowserOnly fallback={<p>Loading…</p>}>
          {() => {
            const PersonalPath =
              require("@site/src/components/personal-path/PersonalPath").default;
            return <PersonalPath />;
          }}
        </BrowserOnly>
      </main>
    </Layout>
  );
}
