import React, { type ReactNode } from "react";
import Content from "@theme-original/DocItem/Content";
import type ContentType from "@theme/DocItem/Content";
import type { WrapperProps } from "@docusaurus/types";
import BrowserOnly from "@docusaurus/BrowserOnly";
import { ModuleFinish, ModulePanel } from "@site/src/components/personal-path/ModulePage";

type Props = WrapperProps<typeof ContentType>;

// Every doc page, with what the learner's personal path says about it above the content, and the module's
// checkpoint and the next module of the path below it.
export default function ContentWrapper(props: Props): ReactNode {
  return (
    <>
      <BrowserOnly>{() => <ModulePanel />}</BrowserOnly>
      <Content {...props} />
      <BrowserOnly>{() => <ModuleFinish />}</BrowserOnly>
    </>
  );
}
