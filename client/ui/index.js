const connectButton = document.getElementById("connect-button")
const disconnectButton = document.getElementById("disconnect-button");
const connectionSection = document.getElementById("connection");
const chatSection = document.getElementById("chat");

const messageForm = document.getElementById("message-form");
const messageInput = document.getElementById("message-input");
const messages = document.getElementById("messages");

const mockMessages = [
    {
        sender: "other",
        text: "hi"
    },
    {
        sender: "me",
        text: "what's up?"
    },
    {
        sender: "other",
        text: "good and u?"
    }
];

const msgs = []
msgs.push(...mockMessages)

connectButton.addEventListener("click", function () {
    // connect(ip, port);
    
    connected(); // remove later
});

disconnectButton.addEventListener("click", function () {
    // disconnect();

    connectionSection.hidden = false
    chatSection.hidden = true
});


/*
 * show empty msgs page
 * show msg saying connected
 */
function connected() {
    connectionSection.hidden = true
    chatSection.hidden = false

    updateChat()
}

function updateChat() {
    const messages = document.getElementById("messages");

    messages.replaceChildren();

    for (const message of msgs) {
        const element = document.createElement("div");

        element.textContent = message.text;

        if (message.sender === "me") {
            element.className = "message message-own";
        } else {
            element.className = "message message-other";
        }

        messages.appendChild(element);
    }
}

/*
 * show text on the left side 
 */
function message_received(text) {
    msgs.push({sender: 'other', text: text});
    updateChat();
}

/*
 * go back to disconnected page 
*/
function disconnected() {
    msgs = []
    connectionSection.hidden = false;
    chatSection.hidden = true;

}

/*
* show error msg on screen 
*/
function error(reason) {
    alert(reason)
}

messageForm.addEventListener("submit", (event) => {
    event.preventDefault();

    message = messageInput.value;

    if (!message) return;

    // For example:
    msgs.push({
        sender: "me",
        text: message
    });

    // function send_message(text);

    messageInput.value = "";

    updateChat();
});