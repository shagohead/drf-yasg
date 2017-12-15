from collections import OrderedDict

from coreapi.compat import urlparse
from future.utils import raise_from
from inflection import camelize

TYPE_OBJECT = "object"  #:
TYPE_STRING = "string"  #:
TYPE_NUMBER = "number"  #:
TYPE_INTEGER = "integer"  #:
TYPE_BOOLEAN = "boolean"  #:
TYPE_ARRAY = "array"  #:
TYPE_FILE = "file"  #:

# officially supported by Swagger 2.0 spec
FORMAT_DATE = "date"  #:
FORMAT_DATETIME = "date-time"  #:
FORMAT_PASSWORD = "password"  #:
FORMAT_BINARY = "binary"  #:
FORMAT_BASE64 = "bytes"  #:
FORMAT_FLOAT = "float"  #:
FORMAT_DOUBLE = "double"  #:
FORMAT_INT32 = "int32"  #:
FORMAT_INT64 = "int64"  #:

# defined in JSON-schema
FORMAT_EMAIL = "email"  #:
FORMAT_IPV4 = "ipv4"  #:
FORMAT_IPV6 = "ipv6"  #:
FORMAT_URI = "uri"  #:

# pulled out of my ass
FORMAT_UUID = "uuid"  #:
FORMAT_SLUG = "slug"  #:

IN_BODY = 'body'  #:
IN_PATH = 'path'  #:
IN_QUERY = 'query'  #:
IN_FORM = 'formData'  #:
IN_HEADER = 'header'  #:

SCHEMA_DEFINITIONS = 'definitions'  #:


def make_swagger_name(attribute_name):
    """
    Convert a python variable name into a Swagger spec attribute name.

    In particular,
     * if name starts with ``x_``, return ``x-{camelCase}``
     * if name is ``ref``, return ``$ref``
     * else return the name converted to camelCase, with trailing underscores stripped

    :param str attribute_name: python attribute name
    :return: swagger name
    """
    if attribute_name == 'ref':
        return "$ref"
    if attribute_name.startswith("x_"):
        return "x-" + camelize(attribute_name[2:], uppercase_first_letter=False)
    return camelize(attribute_name.rstrip('_'), uppercase_first_letter=False)


def _bare_SwaggerDict(cls):
    assert issubclass(cls, SwaggerDict)
    result = cls.__new__(cls)
    OrderedDict.__init__(result)  # no __init__ called for SwaggerDict subclasses!
    return result


class SwaggerDict(OrderedDict):
    """A particular type of OrderedDict, which maps all attribute accesses to dict lookups using
     :func:`.make_swagger_name`. Attribute names starting with ``_`` are set on the object as-is and are not included
     in the specification output.

     Used as a base class for all Swagger helper models.
    """

    def __init__(self, **attrs):
        super(SwaggerDict, self).__init__()
        self._extras__ = attrs
        if type(self) == SwaggerDict:
            self._insert_extras__()

    def __setattr__(self, key, value):
        if key.startswith('_'):
            super(SwaggerDict, self).__setattr__(key, value)
            return
        if value is not None:
            self[make_swagger_name(key)] = value

    def __getattr__(self, item):
        if item.startswith('_'):
            raise AttributeError
        try:
            return self[make_swagger_name(item)]
        except KeyError as e:
            raise_from(AttributeError("object of class " + type(self).__name__ + " has no attribute " + item), e)

    def __delattr__(self, item):
        if item.startswith('_'):
            super(SwaggerDict, self).__delattr__(item)
            return
        del self[make_swagger_name(item)]

    def _insert_extras__(self):
        """
        From an ordering perspective, it is desired that extra attributes such as vendor extensions stay at the
        bottom of the object. However, python2.7's OrderdDict craps out if you try to insert into it before calling
        init. This means that subclasses must call super().__init__ as the first statement of their own __init__,
        which would result in the extra attributes being added first. For this reason, we defer the insertion of the
        attributes and require that subclasses call ._insert_extras__ at the end of their __init__ method.
        """
        for attr, val in self._extras__.items():
            setattr(self, attr, val)

    @staticmethod
    def _as_odict(obj):
        if isinstance(obj, dict):
            result = OrderedDict()
            for attr, val in obj.items():
                result[attr] = SwaggerDict._as_odict(val)
            return result
        elif isinstance(obj, (list, tuple)):
            return type(obj)(SwaggerDict._as_odict(elem) for elem in obj)

        return obj

    def as_odict(self):
        return SwaggerDict._as_odict(self)

    def __reduce__(self):
        # for pickle supprt; this skips calls to all SwaggerDict __init__ methods and relies
        # on the already set attributes instead
        return _bare_SwaggerDict, (type(self),), vars(self), None, iter(self.items())


class Contact(SwaggerDict):
    def __init__(self, name=None, url=None, email=None, **extra):
        """Swagger Contact object

        At least one of the following fields is required:

        :param str name: contact name
        :param str url: contact url
        :param str email: contact e-mail
        """
        super(Contact, self).__init__(**extra)
        if name is None and url is None and email is None:
            raise AssertionError("one of name, url or email is requires for Swagger Contact object")
        self.name = name
        self.url = url
        self.email = email
        self._insert_extras__()


class License(SwaggerDict):
    def __init__(self, name, url=None, **extra):
        """Swagger License object

        :param str name: Required. License name
        :param str url: link to detailed license information
        """
        super(License, self).__init__(**extra)
        if name is None:
            raise AssertionError("name is required for Swagger License object")
        self.name = name
        self.url = url
        self._insert_extras__()


class Info(SwaggerDict):
    def __init__(self, title, default_version, description=None, terms_of_service=None, contact=None, license=None,
                 **extra):
        """Swagger Info object

        :param str title: Required. API title.
        :param str default_version: Required. API version string (not to be confused with Swagger spec version)
        :param str description: API description; markdown supported
        :param str terms_of_service: API terms of service; should be a URL
        :param Contact contact: contact object
        :param License license: license object
        """
        super(Info, self).__init__(**extra)
        if title is None or default_version is None:
            raise AssertionError("title and version are required for Swagger info object")
        if contact is not None and not isinstance(contact, Contact):
            raise AssertionError("contact must be a Contact object")
        if license is not None and not isinstance(license, License):
            raise AssertionError("license must be a License object")
        self.title = title
        self._default_version = default_version
        self.description = description
        self.terms_of_service = terms_of_service
        self.contact = contact
        self.license = license
        self._insert_extras__()


class Swagger(SwaggerDict):
    def __init__(self, info=None, _url=None, _version=None, paths=None, definitions=None, **extra):
        """Root Swagger object.

        :param .Info info: info object
        :param str _url: URL used for guessing the API host, scheme and basepath
        :param str _version: version string to override Info
        :param .Paths paths: paths object
        :param dict[str,.Schema] definitions: named models
        """
        super(Swagger, self).__init__(**extra)
        self.swagger = '2.0'
        self.info = info
        self.info.version = _version or info._default_version

        if _url:
            url = urlparse.urlparse(_url)
            if url.netloc:
                self.host = url.netloc
            if url.scheme:
                self.schemes = [url.scheme]
        self.base_path = '/'

        self.paths = paths
        self.definitions = definitions
        self._insert_extras__()


class Paths(SwaggerDict):
    def __init__(self, paths, **extra):
        """A listing of all the paths in the API.

        :param dict[str,.PathItem] paths:
        """
        super(Paths, self).__init__(**extra)
        for path, path_obj in paths.items():
            assert path.startswith("/")
            if path_obj is not None:  # pragma: no cover
                self[path] = path_obj
        self._insert_extras__()


class PathItem(SwaggerDict):
    def __init__(self, get=None, put=None, post=None, delete=None, options=None,
                 head=None, patch=None, parameters=None, **extra):
        """Information about a single path

        :param .Operation get: operation for GET
        :param .Operation put: operation for PUT
        :param .Operation post: operation for POST
        :param .Operation delete: operation for DELETE
        :param .Operation options: operation for OPTIONS
        :param .Operation head: operation for HEAD
        :param .Operation patch: operation for PATCH
        :param list[.Parameter] parameters: parameters that apply to all operations
        """
        super(PathItem, self).__init__(**extra)
        self.get = get
        self.head = head
        self.post = post
        self.put = put
        self.patch = patch
        self.delete = delete
        self.options = options
        self.parameters = parameters
        self._insert_extras__()


class Operation(SwaggerDict):
    def __init__(self, operation_id, responses, parameters=None, consumes=None,
                 produces=None, description=None, tags=None, **extra):
        """Information about an API operation (path + http method combination)

        :param str operation_id: operation ID, should be unique across all operations
        :param .Responses responses: responses returned
        :param list[.Parameter] parameters: parameters accepted
        :param list[str] consumes: content types accepted
        :param list[str] produces: content types produced
        :param str description: operation description
        :param list[str] tags: operation tags
        """
        super(Operation, self).__init__(**extra)
        self.operation_id = operation_id
        self.description = description
        self.parameters = [param for param in parameters if param is not None]
        self.responses = responses
        self.consumes = consumes
        self.produces = produces
        self.tags = tags
        self._insert_extras__()


class Items(SwaggerDict):
    def __init__(self, type=None, format=None, enum=None, pattern=None, items=None, **extra):
        """Used when defining an array :class:`.Parameter` to describe the array elements.

        :param str type: type of the array elements; must not be ``object``
        :param str format: value format, see OpenAPI spec
        :param list enum: restrict possible values
        :param str pattern: pattern if type is ``string``
        :param .Items items: only valid if `type` is ``array``
        """
        super(Items, self).__init__(**extra)
        self.type = type
        self.format = format
        self.enum = enum
        self.pattern = pattern
        self.items = items
        self._insert_extras__()


class Parameter(SwaggerDict):
    def __init__(self, name, in_, description=None, required=None, schema=None,
                 type=None, format=None, enum=None, pattern=None, items=None, **extra):
        """Describe parameters accepted by an :class:`.Operation`. Each parameter should be a unique combination of
        (`name`, `in_`). ``body`` and ``form`` parameters in the same operation are mutually exclusive.

        :param str name: parameter name
        :param str in_: parameter location
        :param str description: parameter description
        :param bool required: whether the parameter is required for the operation
        :param .Schema,.SchemaRef schema: required if `in_` is ``body``
        :param str type: parameter type; required if `in_` is not ``body``; must not be ``object``
        :param str format: value format, see OpenAPI spec
        :param list enum: restrict possible values
        :param str pattern: pattern if type is ``string``
        :param .Items items: only valid if `type` is ``array``
        """
        super(Parameter, self).__init__(**extra)
        if (not schema and not type) or (schema and type):
            raise AssertionError("either schema or type are required for Parameter object!")
        self.name = name
        self.in_ = in_
        self.description = description
        self.required = required
        self.schema = schema
        self.type = type
        self.format = format
        self.enum = enum
        self.pattern = pattern
        self.items = items
        self._insert_extras__()


class Schema(SwaggerDict):
    OR_REF = ()

    def __init__(self, description=None, required=None, type=None, properties=None, additional_properties=None,
                 format=None, enum=None, pattern=None, items=None, **extra):
        """Describes a complex object accepted as parameter or returned as a response.

        :param description: schema description
        :param list[str] required: list of requried property names
        :param str type: value type; required
        :param list[.Schema,.SchemaRef] properties: object properties; required if `type` is ``object``
        :param bool,.Schema,.SchemaRef additional_properties: allow wildcard properties not listed in `properties`
        :param str format: value format, see OpenAPI spec
        :param list enum: restrict possible values
        :param str pattern: pattern if type is ``string``
        :param .Schema,.SchemaRef items: only valid if `type` is ``array``
        """
        super(Schema, self).__init__(**extra)
        if required is True or required is False:
            # common error
            raise AssertionError(
                "the `requires` attribute of schema must be an array of required properties, not a boolean!")
        self.description = description
        self.required = required
        self.type = type
        self.properties = properties
        self.additional_properties = additional_properties
        self.format = format
        self.enum = enum
        self.pattern = pattern
        self.items = items
        self._insert_extras__()


class _Ref(SwaggerDict):
    def __init__(self, resolver, name, scope, expected_type):
        """Base class for all reference types. A reference object has only one property, ``$ref``, which must be a JSON
        reference to a valid object in the specification, e.g. ``#/definitions/Article`` to refer to an article model.

        :param .ReferenceResolver resolver: component resolver which must contain the referneced object
        :param str name: referenced object name, e.g. "Article"
        :param str scope: reference scope, e.g. "definitions"
        :param type[.SwaggerDict] expected_type: the expected type that will be asserted on the object found in resolver
        """
        super(_Ref, self).__init__()
        assert not type(self) == _Ref, "do not instantiate _Ref directly"
        ref_name = "#/{scope}/{name}".format(scope=scope, name=name)
        obj = resolver.get(name, scope)
        assert isinstance(obj, expected_type), ref_name + " is a {actual}, not a {expected}" \
            .format(actual=type(obj).__name__, expected=expected_type.__name__)
        self.ref = ref_name

    def __setitem__(self, key, value, **kwargs):
        if key == "$ref":
            return super(_Ref, self).__setitem__(key, value, **kwargs)
        raise NotImplementedError("only $ref can be set on Reference objects (not %s)" % key)

    def __delitem__(self, key, **kwargs):
        raise NotImplementedError("cannot delete property of Reference object")


class SchemaRef(_Ref):
    def __init__(self, resolver, schema_name):
        """Adds a reference to a named Schema defined in the ``#/definitions/`` object.

        :param .ReferenceResolver resolver: component resolver which must contain the definition
        :param str schema_name: schema name
        """
        assert SCHEMA_DEFINITIONS in resolver.scopes
        super(SchemaRef, self).__init__(resolver, schema_name, SCHEMA_DEFINITIONS, Schema)


Schema.OR_REF = (Schema, SchemaRef)


class Responses(SwaggerDict):
    def __init__(self, responses, default=None, **extra):
        """Describes the expected responses of an :class:`.Operation`.

        :param dict[(str,int),.Response] responses: mapping of status code to response definition
        :param .Response default: description of the response structure to expect if another status code is returned
        """
        super(Responses, self).__init__(**extra)
        for status, response in responses.items():
            if response is not None:  # pragma: no cover
                self[str(status)] = response
        self.default = default
        self._insert_extras__()


class Response(SwaggerDict):
    def __init__(self, description, schema=None, examples=None, **extra):
        """Describes the structure of an operation's response.

        :param str description: response description
        :param .Schema,.SchemaRef schema: sturcture of the response body
        :param dict examples: example bodies mapped by mime type
        """
        super(Response, self).__init__(**extra)
        self.description = description
        self.schema = schema
        self.examples = examples
        self._insert_extras__()


class ReferenceResolver(object):
    """A mapping type intended for storing objects pointed at by Swagger Refs.
    Provides support and checks for different refernce scopes, e.g. 'definitions'.

    For example:

    ::

        > components = ReferenceResolver('definitions', 'parameters')
        > definitions = ReferenceResolver.with_scope('definitions')
        > definitions.set('Article', Schema(...))
        > print(components)
        {'definitions': OrderedDict([('Article', Schema(...)]), 'parameters': OrderedDict()}
    """

    def __init__(self, *scopes):
        """
        :param str scopes: an enumeration of the valid scopes this resolver will contain
        """
        self._objects = OrderedDict()
        self._force_scope = None
        for scope in scopes:
            assert isinstance(scope, str), "scope names must be strings"
            self._objects[scope] = OrderedDict()

    def with_scope(self, scope):
        """Return a new :class:`.ReferenceResolver` whose scope is defaulted and forced to `scope`.

        :param str scope: target scope, must be in this resolver's `scopes`
        :return: the bound resolver
        :rtype: .ReferenceResolver
        """
        assert scope in self.scopes, "unknown scope %s" % scope
        ret = ReferenceResolver()
        ret._objects = self._objects
        ret._force_scope = scope
        return ret

    def _check_scope(self, scope):
        real_scope = self._force_scope or scope
        if scope is not None:
            assert not self._force_scope or scope == self._force_scope, "cannot overrride forced scope"
        assert real_scope and real_scope in self._objects, "invalid scope %s" % scope
        return real_scope

    def set(self, name, obj, scope=None):
        """Set an object in the given scope, raise an error if it already exists.

        :param str name: reference name
        :param obj: referenced object
        :param str scope: reference scope
        """
        scope = self._check_scope(scope)
        assert obj is not None, "referenced objects cannot be None/null"
        assert name not in self._objects[scope], "#/%s/%s already exists" % (scope, name)
        self._objects[scope][name] = obj

    def setdefault(self, name, maker, scope=None):
        """Set an object in the given scope only if it does not exist.

        :param str name: reference name
        :param callable maker: object factory, called only if necessary
        :param str scope: reference scope
        """
        scope = self._check_scope(scope)
        assert callable(maker), "setdefault expects a callable, not %s" % type(maker).__name__
        ret = self.getdefault(name, None, scope)
        if ret is None:
            ret = maker()
            assert ret is not None, "maker returned None; referenced objects cannot be None/null"
            self.set(name, ret, scope)

        return ret

    def get(self, name, scope=None):
        """Get an object from the given scope, raise an error if it does not exist.

        :param str name: reference name
        :param str scope: reference scope
        :return: the object
        """
        scope = self._check_scope(scope)
        assert name in self._objects[scope], "#/%s/%s is not defined" % (scope, name)
        return self._objects[scope][name]

    def getdefault(self, name, default=None, scope=None):
        """Get an object from the given scope or a default value if it does not exist.

        :param str name: reference name
        :param default: the default value
        :param str scope: reference scope
        :return: the object or `default`
        """
        scope = self._check_scope(scope)
        return self._objects[scope].get(name, default)

    def has(self, name, scope=None):
        """Check if an object exists in the given scope.

        :param str name: reference name
        :param str scope: reference scope
        :return: True if the object exists
        :rtype: bool
        """
        scope = self._check_scope(scope)
        return name in self._objects[scope]

    def __iter__(self):
        if self._force_scope:
            return iter(self._objects[self._force_scope])
        return iter(self._objects)

    @property
    def scopes(self):
        if self._force_scope:
            return [self._force_scope]
        return list(self._objects.keys())

    # act as mapping
    def keys(self):
        if self._force_scope:
            return self._objects[self._force_scope].keys()
        return self._objects.keys()

    def __getitem__(self, item):
        if self._force_scope:
            return self._objects[self._force_scope][item]
        return self._objects[item]

    def __str__(self):
        return str(dict(self))