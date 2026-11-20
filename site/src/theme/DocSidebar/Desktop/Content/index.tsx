import React, { type ReactNode } from "react";
import Content from "@theme-original/DocSidebar/Desktop/Content";
import type ContentType from "@theme/DocSidebar/Desktop/Content";
import type { WrapperProps } from "@docusaurus/types";
import BrowserOnly from "@docusaurus/BrowserOnly";
import { SidebarPathCard } from "@site/src/components/personal-path/Sidebar";

type Props = WrapperProps<typeof ContentType>;

// The docs sidebar, with the learner's path above the course's own navigation.
export default function ContentWrapper(props: Props): ReactNode {
  return (
    <>
      <BrowserOnly>{() => <SidebarPathCard />}</BrowserOnly>
      <Content {...props} />
    </>
  );
}
