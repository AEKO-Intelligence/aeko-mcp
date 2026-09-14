# Reporting tools and customer skill review

Reviewed by Codex on 2026-09-14. MCP implementation: `905588e3ba387a363ebba295ccce7b666714e53f`; companion plugin: `f22f6db55586bd8e92d820b7f9b7f6ff4e4a92f7`.

No blocking findings in this bounded read-only implementation. Code was compared with the deployed backend route signatures, public response schemas, auth dependencies and cursor limits. Product/conversion calls require explicit local account IDs, retain source JSON and null metrics, and expose one page or one stored report without dispatching collection. Account discovery strips credential/SFTP/pixel configuration. Existing delivery-tool behavior is unchanged.

The skill pins the chosen account, keeps a completed account-local comparison window, preserves product identity and pagination limits, and reports conversion coverage/unknown attribution without deriving CPA or ROAS. Brand package/eval references and read-only scheduling behavior remain. The generated catalog changes exactly one document, `aeko-openai-ads-reporting`; legacy backend documents are unchanged. Both commits pass `git diff --check`.

Claude's final verification: 41 new registered-tool tests; 191 passing in the complete MCP suite; 120 registered tools. Plugin catalog check, release-contract lint, cross-repo brand-contract lint and its single catalog test pass. The generic skill quick validator rejects the pre-existing `argument-hint`/`disallowed-tools` frontmatter keys on both base and updated skill; repository compatibility lint is the applicable passing check. No live advertiser read/write pilot was performed for these new tools.

## Coordinated publication still required

These review branches intentionally retain MCP 0.23.0 and plugin 0.29.6 with Unreleased notes. Before publication:

1. Fetch both upstream repositories and check for concurrent releases; preserve the other agent's unfinished MCP structured-result changes in their separate checkout.
2. Select an unused MCP release version and update its release fields (`pyproject.toml`, `server.json`, release notes); merge/tag through the repository flow.
3. Select an unused plugin version, update all five manifests plus release notes, regenerate/check the trusted catalog, and publish its source.
4. Update the app's MCP dependency pin and vendored catalog/hash pins together; validate the resulting app revision and deploy backend. Reconcile defaults through the existing admin endpoint, preserving normal brand-customization update acceptance.

The app's product-reporting/audience release is already live at `71582c6`; these new MCP tools and skill are not in that deployment. This review does not claim package publication or catalog reconciliation has happened.
