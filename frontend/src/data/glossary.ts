/**
 * Glossary of art, provenance, and auction terms.
 * Used by GlossaryText to provide inline hover definitions.
 *
 * Scope: generic recurring jargon only. Do NOT add artist names,
 * specific artwork titles, or other per-analysis content — those are
 * already covered contextually by the agents' own output.
 *
 * Keys are lowercase for matching; definitions are plain-language.
 */

const glossary: Record<string, string> = {
  // Art / Technique
  craquelure: "A network of fine cracks in paint or varnish, typically caused by aging. Its pattern can indicate a painting's age and authenticity.",
  sgraffito: "A technique where a surface layer is scratched through to reveal a contrasting color beneath.",
  punchwork: "Decorative patterns made by punching tools into gold leaf or gesso ground, common in medieval and early Renaissance panel paintings.",
  gesso: "A white primer made of chalk and glue applied to a panel or canvas before painting, providing a smooth surface.",
  tempera: "A fast-drying paint made by mixing pigment with egg yolk or another binder. Dominant medium before oil painting became widespread in the 15th century.",
  gilding: "The application of gold leaf or gold paint to a surface, commonly seen in medieval altarpieces and icon paintings.",
  oilstick: "A solid stick of oil paint mixed with wax, used for drawing directly on surfaces. Associated with Neo-Expressionist artists like Basquiat.",
  patina: "A surface coating that develops over time through aging, oxidation, or use — often valued as evidence of age and authenticity.",
  impasto: "A technique where paint is applied thickly so brushstrokes or palette knife marks are visible, creating texture on the surface.",
  "plein air": "Painting done outdoors, directly from nature, rather than in a studio. Central to Impressionist practice.",
  chiaroscuro: "Strong contrasts between light and dark to create a sense of volume and drama in painting.",
  palette: "The range of colors used by an artist in a particular work or body of work.",
  brushwork: "The visible marks and texture left by an artist's brush, which can indicate technique, period, and authorship.",
  composition: "The arrangement of visual elements within a work — how forms, colors, and space are organized.",

  // Provenance / Legal
  provenance: "The documented ownership history of an artwork, from creation to present. Gaps in provenance can indicate theft, looting, or disputed ownership.",
  attribution: "The scholarly judgment of who created a work. 'Attributed to' indicates probable but not certain authorship.",
  restitution: "The return of a looted or stolen artwork to its rightful owner or their heirs, often after a legal or diplomatic process.",
  forfeiture: "The legal seizure of an artwork by authorities, typically when it's determined to have been stolen or illegally exported.",
  "unesco convention": "The 1970 UNESCO Convention on cultural property, which established international standards against illicit import/export of cultural objects.",
  "red flag": "A documented finding that raises serious concern about an artwork's ownership history or legal status, warranting further investigation.",
  "chain of title": "The complete sequence of documented ownership transfers for an artwork, from creation to current holder.",
  confiscation: "The seizure of property by a government or authority, often used in reference to Nazi-era art theft (1933-1945).",

  // Financial / Auction
  "hammer price": "The final bid price at auction, before buyer's premium and taxes are added. The actual cost to the buyer is typically 20-30% higher.",
  "buyer's premium": "A fee charged by the auction house to the buyer, typically 20-26% of the hammer price, added on top of the winning bid.",
  "illiquidity discount": "A reduction in estimated value accounting for the difficulty of quickly selling an artwork at fair market price.",
  "comparable sale": "A documented sale of a similar artwork used as a reference point for valuation — also called a 'comp.'",
  comp: "Short for 'comparable sale' — a documented auction result for a similar work used as a pricing reference.",
  "valuation corridor": "The range between conservative (floor) and optimistic (ceiling) price estimates for an artwork.",
  "floor estimate": "The conservative low end of a valuation range, typically based on distressed/quick-sale scenarios.",
  "ceiling estimate": "The optimistic high end of a valuation range, typically based on ideal sale conditions (major auction house, competitive bidding).",
  "pre-sale estimate": "The price range an auction house publishes before a sale to set bidder expectations — not a guarantee of the final result.",
  "private treaty": "A sale negotiated directly between parties (or through a dealer), not at public auction — often achieves higher prices than auction for important works.",
};

export default glossary;
