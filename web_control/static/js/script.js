const form = document.getElementById('dataForm');
const textInput = document.getElementById('textInput');
const submitButton = document.getElementById('submitButton');
const stopButton = document.getElementById('stopButton');
const responseMessage = document.getElementById('responseMessage');
const votesRequired = document.getElementById('votesRequired');

const host_url = host_url_main; // 'http://localhost:8080';
const update_interval_msec = update_interval;

// Prevent players from using the back-arrow as it fouls things up during game play.
 history.pushState(null, null, location.href);
 window.onpopstate = function(event)
                    {
                      history.pushState(null, null, location.href);
                      alert('Back navigation is disabled!');
                    }

/*
window.onbeforeunload = function(event) {
    return ("Are you sure you want to leave this page?");
};


window.addEventListener('load', () => {
    // Push state on load
  alert('holy crap');
    history.pushState(null, null, location.href);
    // Add a listener for the popstate event
    window.addEventListener('popstate', (event) => {
        // If user tries to go back, we push the current state again
        history.pushState(null, null, location.href);
        alert("Back navigation is discouraged on this page.");
    });
});
*/

// Function to post form data
async function postData() 
{
  const inputValue = textInput.value;

  // Prepare data to send
  const jsonData = 
  {
    text: inputValue
  };

  try 
  {
    const response = await fetch(host_url+'/submit', 
                                  {
                                    method: 'POST',
                                    headers: {
                                      'Content-Type': 'application/json',
                                    },
                                    body: JSON.stringify(jsonData),
                                  });

    if (!response.ok) 
    {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }

    const result = await response.json();
    // responseMessage.textContent = `Success: ${result.message}`;
  } 
  catch (error) 
  {
    console.error('Error posting data:', error);
    responseMessage.textContent = 'Error submitting data.';
  }
}

async function postStopRequest() 
{
  // Prepare data to send
  const jsonData = 
  {
    text: ''
  };

  try 
  {
    const response = await fetch(host_url+'/requeststop', 
                                  {
                                    method: 'POST',
                                    headers: {
                                      'Content-Type': 'application/json',
                                    },
                                    body: JSON.stringify(jsonData),
                                  });

    if (!response.ok) 
    {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }

    const result = await response.json();
    // responseMessage.textContent = `${result.stoprequests}`;
  } 
  catch (error) 
  {
    console.error('Error posting data:', error);
    responseMessage.textContent = 'Error submitting data: '+error;
  }

}

async function updateStops()
{
  // Prepare data to send
  jsonData = 
  {
    text: ''
  };
  response = await fetch(host_url+'/stopdata', 
                                {
                                  method: 'POST',
                                  headers: {
                                    'Content-Type': 'application/json',
                                    'Access-Control-Allow-Origin': '*',
                                  },
                                  body: JSON.stringify(jsonData),
                                });

  result = await response.json();

  // Note that the enabled state of the buttons is controlled by 0 votes required
  if (result.votes_required > 0)
  {
    stopButton.style.display = 'block';
    winnerButton.style.display = 'block';
    votesRequired.textContent = `Votes needed to skip to next song: ${result.votes_required}`;
  }
  else if (result.votes_required == 0)
  {
    stopButton.style.display = 'none';
    winnerButton.style.display = 'block';
    responseMessage.textContent = '';
    votesRequired.textContent = '';
  }
  else if (result.votes_required == -1)
  {
    stopButton.style.display = 'none';
    winnerButton.style.display = 'none';
    responseMessage.textContent = `The system is waiting for the Game Operator to start it.`;
    votesRequired.textContent = '';

  }
  else if (result.votes_required == -2)
  {
    stopButton.style.display = 'none';
    winnerButton.style.display = 'none';
    responseMessage.textContent = ``;
    votesRequired.textContent = '';

  }

  if (result.votes_required > 0) 
  {
    if (result.stoprequests.length!=0)
    {  
      // responseMessage.textContent = `IDs that have voted: ${result.stoprequests}`;
      responseMessage.textContent = `Votes received so far: ${result.stoprequests.length}`;
    }
    else
    {
      responseMessage.textContent = 'No one has voted to skip this song so far'; 
    }
  }

  console.log('Refresh flags: ',result.refresh_screen[cardNumber])

  if (result.refresh_screen[cardNumber]==true)
  {
    // Issue a synchronous command to clear the refresh flag for this player_nbr
    // Synchronous is important because the flag needs to be clear before the
    // location.refresh() is issued to update the page content. If this call is made
    // asynchronously, the screen flashes a few times while the flag is being cleared.
    const url = host_url+'/clear_refresh'; 
    const requestData = { player_nbr: cardNumber }; // Replace with the actual parameter object
    var response = syncJsonPostRequest(url, requestData); // Making the synchronous POST request
    console.log('Sync XHR response: ',response); // Handle the response as needed
  
    location.reload();
    result.refresh_screen[cardNumber] = false;
    console.log('Reloaded page and reset refresh flag')
  }


}

function syncJsonGetRequest(url) {
    // Create a new instance of XMLHttpRequest
    var xhr = new XMLHttpRequest();
    // Initialize the request: true for async, false for sync. We set it to false.
    xhr.open("GET", url, false); // false makes the request synchronous
    // Set the request header (optional, depending on API requirements)
    xhr.setRequestHeader("Content-Type", "application/json");
    // Send the request
    xhr.send();
    // Check if the request was successful
    if (xhr.status === 200) {
        // Parse and return the JSON response
        return JSON.parse(xhr.responseText);
    } else {
        // Handle errors here
        console.error(`Error ${xhr.status}: ${xhr.statusText}`);
        return null;
    }
}

function syncJsonPostRequest(url, data) {
    // Create a new instance of XMLHttpRequest
    var xhr = new XMLHttpRequest();
    // Initialize the request: specify POST method and set async to false
    xhr.open("POST", url, false); // false makes the request synchronous
    // Set the appropriate request headers
    xhr.setRequestHeader("Content-Type", "application/json");
    // Send the request with JSON-encoded data
    xhr.send(JSON.stringify(data));
    // Check if the request was successful
    if (xhr.status === 200) {
        // Parse and return the JSON response
        return JSON.parse(xhr.responseText);
    } else {
        // Handle errors here
        console.error(`Error ${xhr.status}: ${xhr.statusText}`);
        return null;
    }
}



// Add event listeners to the buttons
// submitButton.addEventListener('click', postData);
stopButton.addEventListener('click', postStopRequest);



// update stop requests every specified number of msec
setInterval(updateStops, 10000); // update_interval_msec);

