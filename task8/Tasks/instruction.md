# Layout regression after upgrading: the app no longer renders the way it did

## What is the current behavior?

An app puts a data table above a row of controls. Neither the application code nor
its stylesheet changed. After upgrading the framework, it renders like this:

![The app as it renders after the upgrade](/app/.harbor_assets/after.png)

## What is the expected behavior?

It should render the way it did before the upgrade:

![The app as it rendered before the upgrade](/app/.harbor_assets/before.png)

The two screenshots are the only description of what regressed: which element is
mis-sized, and where its contents end up, is visible there and stated nowhere else.
Compare them, work out what changed, and fix the layout engine so the app renders as
it did before. The application code and its stylesheet are correct and must not change.

Everything the layout engine gets right today must keep working — in particular,
containers that set an explicit minimum or maximum size must go on placing their
contents exactly as they do now.
