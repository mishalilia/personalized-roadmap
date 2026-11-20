import React, { type ReactNode } from "react";
import clsx from "clsx";
import Link from "@theme-original/DocSidebarItem/Link";
import type LinkType from "@theme/DocSidebarItem/Link";
import type { WrapperProps } from "@docusaurus/types";
import { useSidebarStatus } from "@site/src/components/personal-path/Sidebar";
import "@site/src/components/personal-path/sidebar.css";

type Props = WrapperProps<typeof LinkType>;

// A sidebar link, marked with the module's status in the learner's path (see sidebar.css).
export default function LinkWrapper(props: Props): ReactNode {
  const status = useSidebarStatus(props.item.docId);
  const item = status
    ? { ...props.item, className: clsx(props.item.className, "pp-side", `pp-side--${status}`) }
    : props.item;
  return <Link {...props} item={item} />;
}
