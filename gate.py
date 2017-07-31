#!/usr/bin/env python3

from collections import namedtuple
import re
from lxml import etree as ET
import skll
from collections import Counter
from pprint import pprint

class InputError(Exception):
    pass


class AnnotationFile:
    def __init__(self, filename):
        self.filename = filename
        self.tree = ET.parse(self.filename)
        self.root = self.tree.getroot()
        self._text_with_nodes = self.root.find(".//TextWithNodes")
        self.annotation_set_names = [
            annotation_set.get("Name")
            for annotation_set
            in self.root.findall(".//AnnotationSet")
        ]

    def get_text(self):
        return ''.join(
            ( x for x in self._text_with_nodes.itertext() )
        )

    def iter_annotations(self,
                        *,
                        annotation_types=None,
                        annotation_sets=None):

        if type(annotation_sets) == str:
            annotation_sets = [annotation_sets]
        if type(annotation_types) == str:
            annotation_types = [annotation_types]

        if annotation_sets:
            for annotation_set in annotation_sets:
                annotations = self.root.findall(
                    ''.join(
                        [
                        ".//AnnotationSet[@Name='{}']".format(annotation_set),
                        "/Annotation[@Type='{}']".format(annotation_type)
                        ]
                    )
                )
                for annotation in annotations:
                    yield annotation
        elif annotation_types:
            for annotation_type in annotation_types:
                annotations = self.root.findall(
                    ".//Annotation[@Type='{}']".format(annotation_type)
                )
                for annotation in annotations:
                    yield annotation
        else:
            annotations = self.root.findall(
                ".//Annotation"
            )
            for annotation in annotations:
                yield annotation

        #return AnnotationGroup( Annotation(x) for x in annotations )

class Annotation:
    def __init__(self, annotation):
        self._annotation = annotation
        self._type = annotation.get("Type")
        self._annotation_set = annotation.getparent().get("Name")
        self._id = annotation.get("Id")
        self._start_node = int(annotation.get("StartNode"))
        self._end_node = int(annotation.get("EndNode"))
        self._continuations = []

        if self._type == "Attribution":
            self._caused_event_id = None
            for feature in self.get_features():
                if feature._name == "Caused_Event":
                    self._caused_event_id = feature._value.split()[0]
                    break

    def get_text(self):
        text_with_nodes = self._annotation.getroottree().find(".//TextWithNodes")
        return ''.join(
            x.tail for x in text_with_nodes
            if int(x.get("id")) in range(self._start_node, self._end_node)
        )

    def get_features(self):
        return [ Feature(x) for x in self._annotation if x.tag == "Feature" ]

    def add_continuation(self, annotation):
        self._continuations.append(annotation)


class Feature:
    def __init__(self, feature):
        self._name = feature.find("./Name").text
        self._value = feature.find("./Value").text

class AnnotationGroup:
    def __init__(self, annotation_iterable):
        self._annotations = sorted(
            sorted(
                sorted(
                    annotation_iterable,
                    key=(lambda x: x._annotation_set)
                ),
                key=(lambda x: x._end_node)
            ),
            key=(lambda x: x._type)
        )

        def reverse_find_from_index(iterable, match_function, index):
            for x in sorted(iterable[:index], reverse=True):
                if match_function(x):
                    return x

        for i, annotation in enumerate(self._annotations):
            if "_continuation" in annotation._type:
                continuation = annotation
                base_annotation_type = continuation._type.replace("_continuation","")
                continued_annotation = reverse_find_from_index(
                    annotation,
                    ( lambda x : x._type == base_annotation_type ),
                    i
                )
                continued_annotation.append(annotation)

class Schema:
    def __init__(self, filename):
        self.filename = filename
        self.tree = ET.parse(self.filename)
        self.root = self.tree.getroot()
        self.namespace = {
            'schema':'http://www.w3.org/2000/10/XMLSchema'
        }

    def get_attributes(self, annotation_type):
        attributes = self.root.findall(
            ".//schema:element[@name='{}']"
            "//schema:attribute".format(annotation_type),
            namespaces=self.namespace
        )
        return attributes


def pair_annotations(annotations1,
                     annotations2,
                     *,
                     annotation_type=None,
                     schema=None):

    annotations1_list = list(annotations1)
    annotations2_list = list(annotations2)

    # Build list of annotation pairs
    annotation_pairs = []
    for annotation1 in annotations1_list:
        for annotation2 in annotations2_list:
            # if annotation spans overlap
            if ( ( int(annotation1.get('StartNode')) >= int(annotation2.get('StartNode'))
                    and int(annotation1.get('StartNode')) < int(annotation2.get('EndNode')) )
                    or ( int(annotation1.get('EndNode')) > int(annotation2.get('StartNode'))
                        and int(annotation1.get('EndNode')) <= int(annotation2.get('EndNode')) ) ):
                annotation_pairs.append((annotation1, annotation2))
                annotations2_list.remove(annotation2)
                break
    annotations1_list.clear() and annotations2_list.clear()

    # Unpack Names and Values of each annotation
    content_pairs = []
    for pair in annotation_pairs:
        new_pair = []
        for annotation in pair:
            annotation = { feature.findtext('./Name') : feature.findtext('./Value') for feature in list(annotation) }
            new_pair.append(annotation)
        content_pairs.append(new_pair)

    content_pairs = tuple(content_pairs)

    # Compile comparison sets for each annotation attribute
    ComparisonSet = namedtuple('ComparisonSet', ['attribute', 'annotator1', 'annotator2'])
    attributes = [ attribute.get('name') for attribute in schema.get_attributes(annotation_type) ]
    comparison_sets = []
    for attribute in attributes:
        annotator1 = tuple( annotation_pair[0].get(attribute) for annotation_pair in content_pairs )
        annotator2 = tuple( annotation_pair[1].get(attribute) for annotation_pair in content_pairs )
        attribute_annotations = ComparisonSet(attribute, annotator1, annotator2)
        comparison_sets.append(attribute_annotations)

    # set of annotations that fit the given attribute (attribute_annotations)
    return comparison_sets

def kappa(comparison_set, weights=None):

    if len(comparison_set.annotator1) == len(comparison_set.annotator2):

        new_comparison_set = comparison_set

        if weights == None:
        # skll.kappa accepts only int-like arguments,
        # so, given a set of string annotations, each will
        # be assigned a unique int id.
        # this is only statistically accurate when calculating an unweighted kappa
        # since only then do the distances between annotations not matter.

            # store a set of annotations...
            annotation_dict = {}
            for annotations in [
                comparison_set.annotator1,
                comparison_set.annotator2
            ]:
                for annotation in annotations:
                    annotation_dict.update({annotation : None})

            # then assign ints as ids
            id = 1
            for k in annotation_dict:
                annotation_dict.update({k : str(id)})
                id += 1

            def annotation_int(annotations):
                for annotation in annotations:
                    if annotation in annotation_dict:
                        yield re.sub(
                            annotation,
                            annotation_dict.get(annotation),
                            annotation
                        )

            # replace the annotation strings with int labels
            new_comparison_set = new_comparison_set._replace(
                annotator1=tuple(
                    annotation_int(comparison_set.annotator1)
                ),
                annotator2=tuple(
                    annotation_int(comparison_set.annotator2)
                )
            )

            annotator1 = new_comparison_set.annotator1
            annotator2 = new_comparison_set.annotator2

        else:

            def annotation_int(annotations):
                for annotation in annotations:
                    if annotation:
                        yield re.sub(
                            r'(\d+).*',
                            r'\1',
                            annotation
                        )
                        next()
                    else:
                        yield annotation
                        next()

            new_comparison_set = new_comparison_set._replace(
                annotator1=tuple(
                    annotation_int(comparison_set.annotator1)
                ),
                annotator2=tuple(
                    annotation_int(comparison_set.annotator2)
                )
            )

            annotator1 = new_comparison_set.annotator1
            annotator2 = new_comparison_set.annotator2


        kappa_score = skll.kappa(
            annotator1,
            annotator2,
            weights=weights
        )

        kappa_length = len(new_comparison_set.annotator1)

    return dict(
        {
        'score' : kappa_score,
        'length' : kappa_length
        }
    )

