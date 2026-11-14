import React, { type ReactNode } from "react";
import Content from "@theme-original/DocItem/Content";
import type ContentType from "@theme/DocItem/Content";
import type { WrapperProps } from "@docusaurus/types";
import BrowserOnly from "@docusaurus/BrowserOnly";
import PathBadge from "@site/src/components/personal-path/PathBadge";

type Props = WrapperProps<typeof ContentType>;

// Every doc page, with what the learner's personal path says about it above the content.
export default function ContentWrapper(props: Props): ReactNode {
  return (
    <>
      <BrowserOnly>{() => <PathBadge />}</BrowserOnly>
      <Content {...props} />
    </>
  );
}
