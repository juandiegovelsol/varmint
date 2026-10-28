# Text decorations render at one immutable weight

## Symptom

Every decoration line this library draws over, through or under a text
object comes out at a single hard-coded visual weight. Consumers have no
way, through any public surface, to make those lines heavier or lighter.
The weight is identical for every text object, and identical for every
character inside a text object.

## Visual evidence

Reference renders of the intended result:

- `/app/.harbor_assets/design_ref_1.png`
- `/app/.harbor_assets/design_ref_2.png`
- `/app/.harbor_assets/design_ref_3.png`
- `/app/.harbor_assets/design_ref_4.png`
- `/app/.harbor_assets/design_ref_5.png`
- `/app/.harbor_assets/design_ref_6.png`

## Expected behaviour

Consumers can set the decoration line weight through the library's public
API, and the result matches the reference renders. The renders are
normative for the scope of the change: they show which of the decoration
lines drawn above, through and below the text the setting has to reach,
and how finely the weight is allowed to vary inside a single text object.

- The setting reaches every decoration line the renders show it reaching,
  not only one of them.
- The weight varies inside a single text object at the granularity the
  renders show, not only from one text object to the next.
- The setting survives the library's object round-trip: serialise a text
  object and rebuild it from that data, and the rebuilt object produces
  identical output.
- The setting is observable in the SVG the library emits, so that a
  rendered scene and its serialised SVG agree on the weight actually
  applied.
- The reported weight scales linearly with the setting: triple the
  setting and the weight reported in the emitted SVG triples.
- The weight in force today is the default. A consumer who never sets it
  sees exactly the text they see now, and explicitly setting the default
  is indistinguishable from not setting it at all.
