This is a prototype for si-110 assignment. Here are the instructions to use it: 

We use:

```bash

docker compose build

docker compose up -d db redis mailpit

docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser

docker compose run --rm web python manage.py test recruitment

docker compose up -d web notifications
```

Open:Application: `http://localhost:8000`

Email-based sign-in: `http://localhost:8000/signin/Account`
Registration: `http://localhost:8000/signup/Local`
email viewer: `http://localhost:8025`
Register a recruiter account, then authorize it using:
```bash
docker compose exec web \
  python manage.py authorize_recruiter \
  --email recruiter@example.test \
  --new-company "Example Company"
```
Add another recruiter to that company using the returned company ID:
```bash
docker compose exec web \
  python manage.py authorize_recruiter \
  --email second-recruiter@example.test \
  --company-id 1
```
This grants company membership only, not access to historical submissions. The recruiter generates and manages their age identity outside the application, publishes the public recipient key, and uses the private identity file only in the browser decryption control.

For this platform, use the **age CLI** to generate your recipient key and test encryption/decryption.

## 1. Install age

On macOS with Homebrew:

```bash
brew install age
```

On Debian/Ubuntu, where the package is available:

```bash
sudo apt update
sudo apt install age
```

Alternatively, obtain the CLI from the [official age releases](https://github.com/FiloSottile/age/releases).

## 2. Generate a private identity

```bash
mkdir -p ~/.config/age
chmod 700 ~/.config/age

(
  umask 077
  age-keygen -o ~/.config/age/recruiter.txt
)
```

**Keep `recruiter.txt` private.** Do not upload it to the public-key screen, commit it, or put it in your Docker build directory.

## 3. Get your public recipient key

```bash
age-keygen -y ~/.config/age/recruiter.txt
```

For the browser application, select `~/.config/age/recruiter.txt` in the **public-key management** section for companies. 

