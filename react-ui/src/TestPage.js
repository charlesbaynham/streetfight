
import useSound from 'use-sound';

import beep from './beep.mp3';

const BoopButton = () => {
    const [play] = useSound(beep);

    return <button onClick={play}>Boop!</button>;
};


const TestPage = () => {
    return <>
        <BoopButton />
    </>
};


export default TestPage;
