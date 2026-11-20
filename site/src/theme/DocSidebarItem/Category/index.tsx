import React, { type ReactNode } from "react";
import clsx from "clsx";
import Category from "@theme-original/DocSidebarItem/Category";
import type CategoryType from "@theme/DocSidebarItem/Category";
import type { WrapperProps } from "@docusaurus/types";
import type { PropSidebarItem } from "@docusaurus/plugin-content-docs";
import { useCategorySkipped } from "@site/src/components/personal-path/Sidebar";
import "@site/src/components/personal-path/sidebar.css";

type Props = WrapperProps<typeof CategoryType>;

// The docs a category holds, at any depth.
function docsIn(items: PropSidebarItem[]): string[] {
  return items.flatMap((item) =>
    item.type === "link" ? (item.docId ? [item.docId] : []) : item.type === "category" ? docsIn(item.items) : [],
  );
}

// A sidebar category, marked as skipped when the learner's path leaves out every module in it, so a
// specialization they do not take does not look like part of their path (see sidebar.css).
export default function CategoryWrapper(props: Props): ReactNode {
  const skipped = useCategorySkipped(docsIn(props.item.items));
  const item = skipped ? { ...props.item, className: clsx(props.item.className, "pp-cat--skipped") } : props.item;
  return <Category {...props} item={item} />;
}
