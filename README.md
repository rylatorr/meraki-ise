# Meraki ISE Integration

This proof-of-concept application integrates Cisco Identity Services Engine (ISE) with a Meraki Network.
The goal is to apply group policies to users authenticating onto a network that is not controlled by Meraki gear.

## Preparing ISE

Ensure that you have a recent version (i.e. 2.4 or newer) of ISE deployed and have pxGrid Services enabled.
If you are running ISE 2.6 make sure you have at least version 2.6.0.156-Patch6-20031016. Older versions contain a bug
that prevents pxGrid events from being sent out over the WebSocket.

You will also need to create a client certificate that is used by the application to authenticate with ISE.

1. Launch the ISE Admin GUI using your browser
2. Navigate to Administration -> pxGrid Services
3. Click on the Certificates tab
4. Fill in the form as follows:
   - I want to:                   select "Generate a single certificate (without a certificate signing request)"
   - Common Name (CN):            fill in the name that you want the application to identify as
   - Certificate Download Format: select "Certificate in Privacy Enhanced Electronic Mail (PEM) format, key in PKCS8 PEM format (including certificate chain)"
   - Certificate Password:        fill in a password
   - Confirm Password:            fill in the same password as above
5. Click the 'Create' button. A ZIP file will be offered for download.
6. Extract the downloaded ZIP file. A new folder containing a few certificate files and a keyfile will be created.

From these files we are interested in the following three:
 - Our Client certificate and key: the two files prefixed with the Common Name you chose (.cer and .key)
 - The CA certificate: the file prefixed with the hostname of your ISE instance (.cer)

Before we can use the key file we will have to remove the password:
```
openssl rsa -in <common name>.key -out client.key
```
Enter the key's password to unlock and decrypt the key. Keep the key safe.

## Running the code

The easiest way to run this application is using Docker. Alternatively the code can be run directly using Python.

But before you can run the code you will have to edit the configuration file named `config.yaml` in the `config`
subfolder and ensure that you have all required certificates and keys in place.

Furthermore, in this implementation of the mapper a CSV files that contains the Meraki network IDs and their
corresponding IP subnets is required as well. A sample with the required headings can be found in
`config/networks.sample.csv`.

### Docker

First you need to build the container: 
```
docker-compose build --pull
```

Then you can run the container:

```
docker-compose up
```

Note: If you'd like to run the containers in the background append `-d` to the `docker-compose up` call.

This will also mount the `config` subdirectory from this folder into the container.

### Virtualenv

1. Create a new virtualenv:
   ```
   virtualenv -p python3 venv
   ```
2. Activate virtualenv:
    ```
   . venv/bin/activate
    ```
4. Install requirements:
   ```
   pip install -r requirements.txt
   ```
4. Run application:
   ```
   python meraki-pxgrid.py <config file>
   ```