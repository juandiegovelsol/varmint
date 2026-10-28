# Long option breaks the pop-up list on a narrow screen

## Bug report

### Current Behavior

On a narrow screen, when one of the options is wider than the screen itself, the pop-up list is not drawn correctly:

![current behavior](/app/.harbor_assets/reported.png)

The list also gains a sideways scroll of its own, which we never want: a long option should just be cut off at the far edge.

We ship the app in left-to-right and in right-to-left locales and hit this in both.

### Expected behavior

Here is how it should render instead, and a long list still scrolls up and down:

![expected behavior](/app/.harbor_assets/expected.png)
