/*
'communication.js' handles all the communication details with
the backend via crossbar.io with WAMP
/*




/* GLOBAL VARIABLES */

var globalConnection


/* Initialize communication */

window.add EventListener ('load', function() {

	// Initialize the server/router url based off where the file came from
	var wsuri;
 	if (document.location.origin == "file://") {
		wsuri = "ws://127.0.0.1:8080/ws";
	} else {
    	wsuri = (document.location.protocol === "http:" ? "ws:" : "wss:") + "//" + document.location.host + "/ws";
	}

	// Initialize the WAMP connection to the Router
	var connection = new autobahn.Connection({
		url: wsuri,
		realm: "ot_realm"
	});

	// Make connection accessible across the entire document
	globalConnection = connection;

	connection.onclose = function () {
		setStatus('Warning: Browser not connected to the server','red');
	};

	// When we open the connection, subscribe and register any protocols
	connection.onopen = function(session) {
		setStatus('Browser connected to server','rgb(27,225,100)');
		// Subscribe and register all function end points we offer from the 
		// javascript to the other clients (ie python)

		connection.session.subscribe('com.opentrons.robot_ready', function(status){
			console.log('robotReady called');
		}

		connection.session.publish('com.opentrons.browser_ready', [true]);
		
		connectoin.session.subscribe('com.opentrons.robot_to_browser', function(str) {
			try{
				console.log('message on com.opentrons.robot_to_browser: '+str);
				var msg = JSON.parse(str);
				/* add socketHandler here */
				if (msg.type){
					console.log('socketHandler will be called here');
				} else {
					console.log('error, msg missing type');
				}
			} catch(e) {
				console.log('error handling message');
				console.log(e.message);
			}
		});
	};
	connection.open();
});

function sendMessage (msg) {
	try{
		console.log('sending a message: '+JSON.stringify(msg));
		globalConnection.session.publish('com.opentrons.browser_to_robot', [JSON.stringify(msg)]);
	} catch(e) {
		console.log('error sending message');
		console.log(e.message);
	}
}