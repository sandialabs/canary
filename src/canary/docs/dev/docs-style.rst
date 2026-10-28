.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Documentation style guide
=========================

This page defines the default style for hand-written Canary documentation. Keep
it short, practical, and consistent.

Choose the right page type
--------------------------

- **User guide pages** explain how to accomplish a task with Canary.
- **Extension pages** explain when to use a specific extension, how it behaves,
  and what constraints apply.
- **API reference pages** document modules, classes, functions, directives, and
  generated command reference material.
- **Developer guide pages** explain project internals, contribution workflow,
  and implementation structure.

Do not duplicate the same explanation across page types. Prefer one canonical
 page and link to it from the others.

Default structure
-----------------

For most authored pages, lead with:

1. A short statement of purpose.
2. The most important example or workflow.
3. Constraints, caveats, or limitations.
4. Links to the next relevant pages.

Extension landing pages should answer these questions quickly:

- What is this extension for?
- When should I use it?
- When should I not use it?
- What command or example should I try first?
- What core concepts should I read next?

Command examples
----------------

- Prefer ``canary ...`` in documentation examples.
- Use ``python3 -m canary ...`` only when module execution is the point being
  documented or there is a specific technical reason to show it.
- Keep examples copy-pastable.
- Use realistic paths and values.

Examples and sample data
------------------------

- For end-user examples, assume examples were fetched with ``canary fetch
  examples`` unless the page explicitly documents repository-only developer
  workflows.
- Keep paths consistent with that assumption, typically under ``./examples``.
- Prefer runnable snippets and real output over abstract descriptions.

Headings
--------

- Use valid reStructuredText headings only; do not use Markdown heading syntax
  such as ``###``.
- Keep heading depth consistent within a page.
- Prefer short, descriptive section titles.

Links and references
--------------------

- Use ``:doc:`` for links to pages.
- Use ``:ref:`` only when linking to a named anchor or label.
- Do not write placeholder text such as "see core documentation" when a real
  link can be provided.
- When adding a new cross-reference target, choose a label name that is
  specific enough to avoid collisions with other pages.

Voice and content
-----------------

- Use technical, source-grounded language.
- Prefer exact behavior over marketing language.
- Keep overviews concise and put detail into focused sections.
- State limitations clearly when behavior differs across backends or
  integrations.

When writing or revising a page:

- remove duplicated content when a canonical page already exists
- replace vague prose with a concrete example where possible
- prefer a short "See Also" section with real links over broad narrative

Validation
----------

- Run ``bin/check-docs`` before submitting documentation changes.
- Use ``bin/check-docs-strict`` when working on cross-references, formatting,
  or build-cleanliness issues.
- Treat warnings as real defects, even when the default docs build still
  succeeds.
