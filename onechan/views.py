from datetime import date
from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect,\
    HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.views.generic import View, ListView
from django.shortcuts import get_object_or_404, render
from django.core.urlresolvers import reverse
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db import IntegrityError
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils.http import urlencode
from django.utils import timezone
from django.contrib import messages
from django.contrib.syndication.views import Feed
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from .models import *
from .forms import NewPostForm, NewCommentForm, CommentReactionForm, NewLinkForm
from .utils import notify
from .utils.stats import update_posting_stats


@method_decorator(ensure_csrf_cookie, name='dispatch')
class PostsListView(View):
    filters = {
        'approved': Q(status=Post.APPROVED),
        'hidden': Q(status=Post.HIDDEN),
        'all': Q(status=Post.ALL) | Q(status=Post.APPROVED)
    }

    titles = {
        'approved': 'Одобренные новости',
        'hidden': 'Скрытые новости',
        'all': 'Все новости'
    }

    def get_queryset(self, request, *args, **kwargs):
        return Post.objects.select_related('category').filter(self.filters[kwargs['posts_type']])

    def get_title(self, request, *args, **kwargs):
        return self.titles[kwargs['posts_type']]

    def get(self, request, *args, **kwargs):
        sort_by_bump = request.GET.get("sort_by_bump", '') in ['1', 'true']
        pgtr = Paginator(self.get_queryset(request, *args, **kwargs)\
            .order_by('-pinned', '-bump_date' if sort_by_bump else '-pub_date'), 10)
        page = request.GET.get("page")
        try:
            posts = pgtr.page(page)
        except PageNotAnInteger:
            posts = pgtr.page(1)
        except EmptyPage:
            return HttpResponseRedirect(request.path +
                '?' + urlencode({'page': pgtr.num_pages}))
        links = Link.objects.filter(pub_date__date=date.today()).order_by('-pub_date')
        return render(request, "onechan/posts_list.html", {
            'posts': posts,
            'links': links,
            'title': self.get_title(request, *args, **kwargs)
        })


@method_decorator(ensure_csrf_cookie, name='dispatch')
class FavouritesListView(PostsListView):

    def get_queryset(self, request, *args, **kwargs):
        return Post.objects.filter(favourite__user_ip=request.META['REMOTE_ADDR'])

    def get_title(self, request, *args, **kwargs):
        return 'Избранные новости'


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CategoryListView(PostsListView):

    def get_queryset(self, request, *args, **kwargs):
        self.cat = get_object_or_404(Category, pk=kwargs.get('category_id'))
        return Post.objects.filter(category=self.cat)

    def get_title(self, request, *args, **kwargs):
        return 'Новости в категории {}'.format(self.cat.name)


def index(request):
    return redirect(reverse('onechan:approved_posts'), permanent=True)

def category_list(request):
    return render(request, 'onechan/category_list.html',
        {'categories': Category.objects.all()})

def show_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    ip = request.META['REMOTE_ADDR']
    post.add_viewer(ip)
    return render(request, 'onechan/post.html', {
        'post': post,
        'comment_form': NewCommentForm(ip=ip),
        'react_form': CommentReactionForm(),
    })

def add_post(request):
    if request.method == 'GET':
        return render(request, 'onechan/add_post.html', {'form': NewPostForm()})
    elif request.method == 'POST':
        post = Post(author_ip=request.META['REMOTE_ADDR'])
        form = NewPostForm(request.POST, instance=post)
        if form.is_valid():
            post = form.save()
            post_url = reverse('onechan:show_post', kwargs={'post_id': post.id})
            msg = {
                'type': 'new_post',
                'data': {
                    'title': post.title,
                    'url' : post_url,
                }
            }
            if post.category:
                msg['data']['category'] = post.category.name
            notify(msg)
            update_posting_stats()
            return redirect(post_url)
        else:
            return render(request, 'onechan/add_post.html', status=400, context={
                'form': form
                })

def last_comments(request):
    comments = Comment.objects.select_related('post').select_related('author_board')\
        .prefetch_related('reaction_set__image').order_by('-pk')[:20]
    return render(request, 'onechan/last_comments.html', {
        'comments': comments,
        'react_form': CommentReactionForm(),
    })

def add_comment(request, post_id):
    if request.method == 'POST':
        post = get_object_or_404(Post, pk=post_id)
        if post.closed:
            return HttpResponseForbidden()
        ip = request.META['REMOTE_ADDR']
        comment = Comment(author_ip=ip, post=post)
        form = NewCommentForm(request.POST, ip=ip, instance=comment)
        if form.is_valid():
            form.save()
            if post.bumpable:
                post.bump_date = timezone.now()
            post.save()
            notify({
                'type': 'new_comment',
                'room': 'news_' + post_id,
                'data': {
                    'id': comment.id,
                    'post_id': post_id,
                    'html': render_to_string(
                        'onechan/comment_partial.html',
                        context={'comment': comment},
                        request=request
                    )
                }
            })
            update_posting_stats()
            return JsonResponse({
                'success': True,
                'captcha_required': NewCommentForm.is_captcha_required(ip),
            })
        else:
            return JsonResponse({
                'success': False,
                'errors': form.errors,
                'captcha_required': NewCommentForm.is_captcha_required(ip),
            }, status=400)
    else:
        return HttpResponseNotAllowed(['POST'])

def get_comment(request, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id)
    return JsonResponse({
        'success': True,
        'html': render_to_string(
            'onechan/comment_partial.html',
            context={'comment': comment},
            request=request
        )
    })

def comment_react(request, comment_id):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    form = CommentReactionForm(request.POST)
    if form.is_valid():
        comment = Comment.objects.get(pk=comment_id)
        r = Reaction(
            image=form.cleaned_data['image'],
            user=request.anon_user,
            comment=comment,
        )
        try:
            r.save()
        except IntegrityError:
            return JsonResponse({
                'success': False,
                'error': 'already_reacted',
            })
        notify({
            'type': 'new_reaction',
            'room': 'news_' + str(comment.post_id),
            'data': {
                'id': comment.id,
                'name': r.image.name,
                'img': r.image.img.url,
            }
        })
    return JsonResponse({
        'success': True
    })

def rate_post(request, post_id):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    post = get_object_or_404(Post, pk=post_id)
    ip = request.META['REMOTE_ADDR']
    value = 1 if int(request.POST.get('value', -1)) == 1 else -1
    if post.rate(ip, value):
        notify({
            'type': 'new_rating',
            'data': {
                'post_id': post_id,
                'rating': post.rating
            }
        })
        return JsonResponse({'success': True})
    else:
        return JsonResponse({'success': False, 'error': 'had_voted'}, status=403)

def set_favourite(request, post_id):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    post = get_object_or_404(Post, pk=post_id)
    ip = request.META['REMOTE_ADDR']
    value = request.POST.get('value') in ['1', 'true']
    post.set_favourite(ip, value)
    return JsonResponse({
        'success': True,
        'favourite': value,
        'post_id': post.id
    })


class LinksListView(ListView):
    model = Link
    queryset = Link.objects.order_by('-id')
    template_name = 'onechan/links_list.html'
    paginate_by = 10
    context_object_name = 'links'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['link_form'] = NewLinkForm()
        return context


def add_link(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    form = NewLinkForm(request.POST)
    if form.is_valid():
        link = form.save(commit=False)
        link.author = request.anon_user
        link.save()
        return redirect(reverse('onechan:links'))
    else:
        return render(request, 'onechan/links_list.html', {'link_form': form})


class NewsFeed(Feed):

    title = 'Одобренные новости'
    description = ''

    def __init__(self, all=False):
        super(NewsFeed, self).__init__()
        self.all = all

    def link(self):
        return reverse('onechan:approved_posts' if not self.all else 'onechan:all_posts')

    def items(self):
        if not self.all:
            return Post.objects.filter(status=Post.APPROVED).order_by('-pub_date')[:10]
        else:
            return Post.objects.filter(Q(status=Post.APPROVED) | Q(status=Post.ALL))\
                .order_by('-pub_date')[:10]

    def item_link(self, item):
        return reverse('onechan:show_post', kwargs={'post_id': item.id})

    def item_title(self, item):
        if item.category:
            return '{} → {}'.format(item.category.name, item.title)
        else:
            return item.title

    def item_description(self, item):
        return render_to_string('onechan/post_rss.html', context={'post': item})

    def item_pubdate(self, item):
        return item.pub_date

    def item_categories(self, item):
        return [item.category.name] if item.category else []


def markup_help(request):
    smileys = Smiley.objects.all()
    examples = [
        '# Заголовок первого уровня',
        '## Заголовок второго уровня',
        '### Заголовок третьего уровня',
        '> цитата',
        '* элемент списка\n* элемент списка\n* элемент списка',
        '1. элемент списка\n2. элемент списка\n3. элемент списка',
        '    это\n    абзац\n    с кодом',
        '***',
        'тут *курсивный* текст',
        'тут **жирный** текст',
        'тут `моноширинный` текст',
        r'%%спойлер%%',
        '>>1',
        '[текст ссылки](https://example.org "Эта ссылка ведет на example.org")',
        '![Пример картинки](https://i.imgur.com/uORVhj7.jpg ":3")\n\n'
            'Администратор сайта может ограничивать источники картинок.',
        '\*\*Используйте \\ для эскейпинга.\*\*',
    ]
    examples += [ ':{}:'.format(s.name) for s in smileys]
    return render(request, 'onechan/markup_help.html', {'examples': examples})
