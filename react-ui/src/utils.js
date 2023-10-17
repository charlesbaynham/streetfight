import gun_11 from './images/guns/gun_11.png';
import gun_16 from './images/guns/gun_default.png';
import gun_26 from './images/guns/gun_26.png';
import gun_36 from './images/guns/gun_36.png';


export function makeAPIURL(endpoint, query_params = null) {
    const url = new URL(`/api/${endpoint}`, window.location.origin);

    if (query_params) {
        Object.keys(query_params).forEach(key => url.searchParams.append(key, query_params[key]))
    }

    return url
}

export function sendAPIRequest(endpoint, query_params = null, method = 'GET', callback = null, post_object = null) {
    const url = makeAPIURL(endpoint, query_params)

    var requestOptions;
    if (post_object !== null) {
        const query = JSON.stringify(post_object);

        requestOptions = {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: query
        };
    } else {
        requestOptions = {
            method: method,
            headers: { 'Content-Type': 'application/json' },
        };
    }

    // Callbacks are only called on success
    // To handle errors, use the returned promise which gives the raw response
    return fetch(url, requestOptions)
        .then(async response => {
            if (callback) {
                if (!response.ok) {
                    console.log(`Error in api call to ${url}:`)
                    console.dir(response)
                    console.dir(response.json())
                } else {
                    callback(await response.json())
                }
            }
            return response;
        });
}

export function getGunImgFromUser(user) {
    let gun_name = null;

    if (user.shot_damage === 1 && user.shot_timeout === 6)
        gun_name = "damage1";
    else if (user.shot_damage === 2 && user.shot_timeout === 6)
        gun_name = "damage2";
    else if (user.shot_damage === 3 && user.shot_timeout === 6)
        gun_name = "damage3";
    else if (user.shot_damage === 1 && user.shot_timeout === 1)
        gun_name = "fast1";
    else
        return null


    const GUN_IMGS = {
        "damage1": gun_16,
        "damage2": gun_26,
        "damage3": gun_36,
        "fast1": gun_11,
    };

    return GUN_IMGS[gun_name];
}
