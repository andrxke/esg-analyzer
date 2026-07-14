/** Shared mapping from a verdict label to its presentation. */

function modifier(label: string | null): string {
  switch (label) {
    case "Recommended":
      return "recommended";
    case "Improving":
      return "improving";
    case "Not Recommended":
      return "not-recommended";
    default:
      return "recommended";
  }
}

/** The loud, rotated rubber-stamp used once per verdict page. */
export function stampClass(label: string | null): string {
  return `stamp stamp--${modifier(label)}`;
}

/** The quiet inline chip used in the ledger / lists. */
export function chipClass(label: string | null): string {
  return `chip chip--${modifier(label)}`;
}

/** The mono tag line printed above the verdict on the stamp. */
export function stampTag(label: string | null): string {
  switch (label) {
    case "Recommended":
      return "Assessed · clears rubric";
    case "Improving":
      return "Assessed · tells present";
    case "Not Recommended":
      return "Assessed · major tells";
    default:
      return "Assessed";
  }
}

/** One-line gloss so "Recommended" is never read as an endorsement. */
export function labelGloss(label: string | null): string {
  switch (label) {
    case "Recommended":
      return "No major greenwashing tells found in this report. Not an endorsement.";
    case "Improving":
      return "Some greenwashing tells present, but not enough for Not Recommended.";
    case "Not Recommended":
      return "Multiple major greenwashing tells found in this report.";
    default:
      return "";
  }
}
