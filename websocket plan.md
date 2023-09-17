websock plan
=====

1. Server will have an API endpoint e.g. "sse_updates"
2. This will send out prompts to update components, in the format e.g.:
```
{
    handler: "update_prompt",
    data: "user"
}
```

This format should be future-compatible in case I want to add more SSE functionality later.
3. The client will listen to this socket and will fire the associated update when requested.
4. It only needs to handle updates, so hashes no longer are needed on the client - on load we'll be up to date anyway. Maybe I should send out initial update messages when the socket is opened to make sure.


Plan for the frontend:

1. Adapt HashUpdater to take a "type" and a "callback" - the callback fires on updates to "type"
2. Each HashUpdater object registers itself to a variable in the HashUpdater module as a listener of "type"
3. When an event is received on the SSE, all listeners of that type are fired
