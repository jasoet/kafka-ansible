// Code block styling - gray box with border
#show raw.where(block: true): it => {
  set par(justify: false)
  block(
    fill: rgb("#f6f8fa"),
    stroke: (paint: rgb("#d0d7de"), thickness: 1pt),
    inset: 12pt,
    radius: 6pt,
    width: 100%,
    breakable: true,
  )[
    #set text(font: "Menlo", size: 8.5pt)
    #it
  ]
}

// Inline code styling
#show raw.where(block: false): it => {
  box(
    fill: rgb("#eff1f3"),
    inset: (x: 4pt, y: 0pt),
    outset: (y: 3pt),
    radius: 3pt,
  )[#text(font: "Menlo", size: 9pt)[#it]]
}

// Blockquote styling
#show quote.where(block: true): it => {
  block(
    fill: rgb("#fff8e6"),
    stroke: (left: 4pt + rgb("#f0b429")),
    inset: (left: 14pt, right: 12pt, y: 10pt),
    width: 100%,
    radius: (right: 4pt),
  )[#it.body]
}

// Table styling - breakable across pages
#show figure.where(kind: table): set figure.caption(position: top)
#show figure.where(kind: table): set block(breakable: true)
#show table.cell.where(y: 0): set text(weight: "bold")
#set table(
  inset: 8pt,
  stroke: (paint: rgb("#d0d7de"), thickness: 0.5pt),
  fill: (_, y) => if y == 0 { rgb("#f6f8fa") },
)

// Horizontal rule spacing
#show line: it => {
  block(above: 1.2em, below: 1.2em)[#it]
}

// Heading spacing
#show heading.where(level: 1): it => {
  block(above: 1.5em, below: 0.5em)[
    #text(size: 16pt, weight: "bold")[#it]
  ]
}

#show heading.where(level: 2): it => {
  block(above: 1.2em, below: 0.6em)[
    #text(size: 13pt, weight: "bold")[#it]
  ]
}

#show heading.where(level: 3): it => {
  block(above: 1em, below: 0.5em)[
    #text(size: 11pt, weight: "bold")[#it]
  ]
}

// Page footer
#set page(
  footer: context {
    set text(size: 9pt, fill: rgb("#57606a"))
    h(1fr)
    counter(page).display("1")
    h(1fr)
  }
)
