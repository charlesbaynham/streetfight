
export function sendAPIRequest(endpoint, query_params = null, method = 'GET', callback = null) {
    const url = new URL(`/api/${endpoint}`, document.baseURI);

    if (query_params) {
        Object.keys(query_params).forEach(key => url.searchParams.append(key, query_params[key]))
    }

    const requestOptions = {
        method: method,
        headers: { 'Content-Type': 'application/json' },
    };

    fetch(url, requestOptions)
        .then(response => {
            if (!response.ok) {
                console.log(`Error in api call to ${url}:`)
                console.dir(response)
                console.dir(response.json())
                return null
            }
            return response.json()
        })
        .then(data => {
            if (callback) {
                callback(data);
            }
        });
}


export const SCREEN_FILL_STYLES = {
    position: "absolute",
    height: "100vh",
    width: "100vw",
    left: "0",
    top: "0",
    zIndex: -1
};


export default null;
