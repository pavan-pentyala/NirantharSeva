/** Where a role lands after login. Screens 4 and 6 are P4.2 placeholders
 * (Phase 5 and Phase 6 build them for real) — see docs/PHASE4_PLAN.md's
 * screen-scope decision. */
export function homeRouteFor(role: string): string {
  switch (role) {
    case "ASHA":
      return "/referrals";
    case "MO":
      return "/mo/incoming";
    case "ANM":
      return "/identity-review";
    case "SUPERVISOR":
      return "/supervisor";
    default:
      return "/login";
  }
}
