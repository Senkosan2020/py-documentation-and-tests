import io
from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from cinema.models import Actor, Genre, Movie

MOVIES_URL = reverse("cinema:movie-list")


def detail_url(movie_id: int) -> str:
    return reverse("cinema:movie-detail", args=[movie_id])


def upload_image_url(movie_id: int) -> str:
    return reverse("cinema:movie-upload-image", args=[movie_id])


def sample_genre(name: str = "Drama") -> Genre:
    return Genre.objects.create(name=name)


def sample_actor(first_name: str = "Emma", last_name: str = "Watson") -> Actor:
    return Actor.objects.create(first_name=first_name, last_name=last_name)


def sample_movie(
    title: str = "Sample movie",
    description: str = "Sample description",
    duration: int = 90,
) -> Movie:
    return Movie.objects.create(title=title, description=description, duration=duration)


class PublicMovieViewSetTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def test_auth_required_for_list(self) -> None:
        res = self.client.get(MOVIES_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_auth_required_for_detail(self) -> None:
        movie = sample_movie()
        res = self.client.get(detail_url(movie.id))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateMovieViewSetTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email="user@example.com", password="testpass123"
        )
        self.client.force_authenticate(self.user)

    def test_list_movies_success(self) -> None:
        sample_movie(title="Alpha")
        sample_movie(title="Beta")
        res = self.client.get(MOVIES_URL)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res.data, list)
        self.assertGreaterEqual(len(res.data), 2)
        self.assertIn("id", res.data[0])
        self.assertIn("title", res.data[0])
        self.assertIn("genres", res.data[0])
        self.assertIn("actors", res.data[0])
        self.assertIn("image", res.data[0])
        titles = sorted([item["title"] for item in res.data])
        self.assertEqual(titles, ["Alpha", "Beta"])

    def test_retrieve_movie_success(self) -> None:
        movie = sample_movie("Detail")
        g1 = sample_genre("Drama")
        g2 = sample_genre("Fantasy")
        a1 = sample_actor("Emma", "Watson")
        a2 = sample_actor("Daniel", "Radcliffe")
        movie.genres.add(g1, g2)
        movie.actors.add(a1, a2)

        res = self.client.get(detail_url(movie.id))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res.data.get("genres"), list)
        self.assertIsInstance(res.data.get("actors"), list)
        self.assertIn("image", res.data)

    def test_filter_by_title_icontains(self) -> None:
        m1 = sample_movie(title="Liar Liar")
        m2 = sample_movie(title="Inception")
        res = self.client.get(MOVIES_URL, {"title": "liar"})

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        titles = [m["title"] for m in res.data]
        self.assertIn(m1.title, titles)
        self.assertNotIn(m2.title, titles)

    def test_filter_by_genres(self) -> None:
        g1 = sample_genre("Drama")
        g2 = sample_genre("Comedy")
        m1 = sample_movie(title="A")
        m2 = sample_movie(title="B")
        m1.genres.add(g1)
        m2.genres.add(g2)

        res = self.client.get(MOVIES_URL, {"genres": str(g1.id)})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        titles = [m["title"] for m in res.data]
        self.assertIn("A", titles)
        self.assertNotIn("B", titles)

    def test_filter_by_actors(self) -> None:
        a1 = sample_actor("Tom", "Hardy")
        a2 = sample_actor("Emma", "Stone")
        m1 = sample_movie(title="A")
        m2 = sample_movie(title="B")
        m1.actors.add(a1)
        m2.actors.add(a2)

        res = self.client.get(MOVIES_URL, {"actors": str(a1.id)})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        titles = [m["title"] for m in res.data]
        self.assertIn("A", titles)
        self.assertNotIn("B", titles)

    def test_non_admin_cannot_create_movie(self) -> None:
        payload: Dict[str, Any] = {
            "title": "New",
            "description": "Desc",
            "duration": 120,
            "genres": [],
            "actors": [],
        }
        res = self.client.post(MOVIES_URL, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_image_field_not_accepted_on_post(self) -> None:
        buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buf, format="JPEG")
        buf.seek(0)
        payload = {
            "title": "WithImage",
            "description": "X",
            "duration": 90,
            "genres": [],
            "actors": [],
            "image": ContentFile(buf.read(), name="bad.jpg"),
        }
        res = self.client.post(MOVIES_URL, payload, format="multipart")
        self.assertIn(res.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN))


class AdminMovieViewSetTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.admin = get_user_model().objects.create_superuser(
            email="admin@example.com", password="adminpass123"
        )
        self.client.force_authenticate(self.admin)

    def test_admin_can_create_movie(self) -> None:
        g = sample_genre("Drama")
        a = sample_actor("Emma", "Watson")
        payload = {
            "title": "Created",
            "description": "Created desc",
            "duration": 100,
            "genres": [g.id],
            "actors": [a.id],
        }
        res = self.client.post(MOVIES_URL, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        movie = Movie.objects.get(id=res.data["id"])
        self.assertEqual(movie.title, "Created")
        self.assertIn(g, movie.genres.all())
        self.assertIn(a, movie.actors.all())

    def test_upload_image_success(self) -> None:
        movie = sample_movie("Liar")
        buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buf, format="JPEG")
        buf.seek(0)

        res = self.client.post(
            upload_image_url(movie.id),
            {"image": ContentFile(buf.read(), name="test.jpg")},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        movie.refresh_from_db()
        self.assertTrue(bool(movie.image))

    def test_upload_image_invalid(self) -> None:
        movie = sample_movie("BadUpload")
        res = self.client.post(
            upload_image_url(movie.id),
            {"image": "not-an-image"},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
