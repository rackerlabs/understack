# Proposals

This section holds design proposals for UnderStack: write-ups that capture a
problem, the options considered, and the decision, before the code is written.
They follow an ADR-style format so the reasoning survives after the change ships.

A proposal moves through `provisional` (drafted, under discussion),
`implementable` (agreed, being built), `implemented` (shipped), or `rejected`
(recorded so we don't relitigate it).

Once a proposal is implemented, the operational detail belongs in the
[Operator Guide](../operator-guide/index.md) or
[Design Guide](../design-guide/intro.md). The proposal stays here as the record
of why.

## Current Proposals

| Proposal | Status | Summary |
|----------|--------|---------|
| [Nautobot Resource Sync (ipsync)](ipsync.md) | provisional | Static vs dynamic data ownership between the deploy repo, Nautobot, and each site's OpenStack, plus validation and site read-back. |
