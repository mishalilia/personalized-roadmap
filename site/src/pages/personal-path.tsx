import React, { useEffect, type ReactNode } from "react";
import Layout from "@theme/Layout";
import { useHistory } from "@docusaurus/router";
import { setDrawer } from "@site/src/components/personal-path/store";

// The personal path lives in a panel beside the course (src/components/personal-path/PathDrawer.tsx). This
// address, from earlier links and bookmarks, opens the course with the panel open.
export default function PersonalPathPage(): ReactNode {
  const history = useHistory();
  useEffect(() => {
    setDrawer(true);
    history.replace("/docs/");
  }, [history]);
  return (
    <Layout title="My path" description="Your personal path through the curriculum.">
      <main className="container margin-vert--xl" />
    </Layout>
  );
}
